"""Persisted server-owned notebook grants, separate from corpus identity.

Existing notebooks are deliberately not auto-enrolled. An authenticated
operator/onboarding workflow must explicitly grant actors before serving them.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from mnemo.interfaces import DependencyUnavailableError, NotFoundError
from mnemo.models import FrozenMetadata, Notebook
from mnemo.models._shared import thaw_json


class NotebookScopeAuthority(Protocol):
    def permits(self, actor_id: UUID, notebook_id: UUID) -> bool: ...


class SQLiteNotebookScopeAuthority:
    """Small operational ACL store; no lookup grants access by default."""

    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise ValueError("scope authority path must be absolute")
        self.path = path.resolve(strict=False)
        self._source_lock_path = self.path.with_name(self.path.name + ".source-lock.db")
        self._active_source_leases: dict[object, sqlite3.Connection] = {}

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
                "status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','unverified')), "
                "granted_by TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "PRIMARY KEY(actor_id,notebook_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS retired_notebook_ids("
                "notebook_id TEXT PRIMARY KEY, retired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notebook_acl_revisions("
                "notebook_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision > 0))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notebook_create_intents("
                "notebook_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, token TEXT NOT NULL UNIQUE, "
                "payload TEXT)"
            )
            if "payload" not in {
                row[1] for row in connection.execute("PRAGMA table_info(notebook_create_intents)")
            }:
                connection.execute("ALTER TABLE notebook_create_intents ADD COLUMN payload TEXT")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notebook_create_completions("
                "notebook_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, token TEXT NOT NULL UNIQUE)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS final_qa_v1_acl_bindings("
                "assistant_turn_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, "
                "notebook_id TEXT NOT NULL, session_id TEXT NOT NULL, "
                "user_turn_id TEXT NOT NULL, acl_revision INTEGER NOT NULL "
                "CHECK(acl_revision > 0), document_scopes TEXT)"
            )
            if "document_scopes" not in {
                row[1] for row in connection.execute("PRAGMA table_info(final_qa_v1_acl_bindings)")
            }:
                connection.execute(
                    "ALTER TABLE final_qa_v1_acl_bindings ADD COLUMN document_scopes TEXT"
                )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS source_ingestion_intents("
                "notebook_id TEXT NOT NULL, content_hash TEXT NOT NULL, "
                "actor_id TEXT NOT NULL, token TEXT NOT NULL UNIQUE, "
                "state TEXT NOT NULL CHECK(state IN "
                "('incomplete','published','failed','quarantined','recoverable')), "
                "source_id TEXT, lock_protocol_version INTEGER NOT NULL DEFAULT 0, "
                "document_preexisted INTEGER NOT NULL DEFAULT 1 "
                "CHECK(document_preexisted IN (0,1)), "
                "PRIMARY KEY(notebook_id,content_hash))"
            )
            if "lock_protocol_version" not in {
                row[1] for row in connection.execute("PRAGMA table_info(source_ingestion_intents)")
            }:
                connection.execute(
                    "ALTER TABLE source_ingestion_intents ADD COLUMN "
                    "lock_protocol_version INTEGER NOT NULL DEFAULT 0"
                )
            if "document_preexisted" not in {
                row[1] for row in connection.execute("PRAGMA table_info(source_ingestion_intents)")
            }:
                connection.execute(
                    "ALTER TABLE source_ingestion_intents ADD COLUMN "
                    "document_preexisted INTEGER NOT NULL DEFAULT 1"
                )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS source_deletion_intents("
                "source_id TEXT PRIMARY KEY, notebook_id TEXT NOT NULL, "
                "document_id TEXT NOT NULL, actor_id TEXT NOT NULL, "
                "token TEXT NOT NULL UNIQUE, state TEXT NOT NULL "
                "CHECK(state IN ('deleting','deleted')))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS source_ingestion_asset_candidates("
                "notebook_id TEXT NOT NULL, source_content_hash TEXT NOT NULL, "
                "asset_hash TEXT NOT NULL, mime_type TEXT NOT NULL, "
                "preexisting INTEGER NOT NULL CHECK(preexisting IN (0,1)), "
                "PRIMARY KEY(notebook_id,source_content_hash,asset_hash,mime_type))"
            )
            connection.commit()
        finally:
            connection.close()
        with closing(sqlite3.connect(self._source_lock_path)) as lock_connection:
            lock_connection.execute(
                "CREATE TABLE IF NOT EXISTS source_operation_lock(identity INTEGER PRIMARY KEY)"
            )
            lock_connection.commit()

    def migrate_legacy_grants_unverified(self) -> None:
        """Explicit, transactional migration; never attest pre-existing grants.

        Invoke only after an operator has selected and backed up the exact ACL
        store. This is not called by runtime startup or by ``initialize``.
        """
        if not self.path.is_file():
            raise RuntimeError("scope authority has not been initialized")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(notebook_grants)")}
            if not {"actor_id", "notebook_id", "role", "granted_by"} <= columns:
                raise RuntimeError("unknown notebook grant schema")
            if "status" not in columns:
                connection.execute(
                    "ALTER TABLE notebook_grants ADD COLUMN status TEXT NOT NULL "
                    "DEFAULT 'unverified' "
                    "CHECK(status IN ('active','unverified'))"
                )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notebook_acl_revisions("
                "notebook_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision > 0))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notebook_create_intents("
                "notebook_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, token TEXT NOT NULL UNIQUE, "
                "payload TEXT)"
            )
            if "payload" not in {
                row[1] for row in connection.execute("PRAGMA table_info(notebook_create_intents)")
            }:
                connection.execute("ALTER TABLE notebook_create_intents ADD COLUMN payload TEXT")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notebook_create_completions("
                "notebook_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, token TEXT NOT NULL UNIQUE)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS source_ingestion_intents("
                "notebook_id TEXT NOT NULL, content_hash TEXT NOT NULL, "
                "actor_id TEXT NOT NULL, token TEXT NOT NULL UNIQUE, "
                "state TEXT NOT NULL CHECK(state IN "
                "('incomplete','published','failed','quarantined','recoverable')), "
                "source_id TEXT, lock_protocol_version INTEGER NOT NULL DEFAULT 0, "
                "document_preexisted INTEGER NOT NULL DEFAULT 1 "
                "CHECK(document_preexisted IN (0,1)), "
                "PRIMARY KEY(notebook_id,content_hash))"
            )
            if "lock_protocol_version" not in {
                row[1] for row in connection.execute("PRAGMA table_info(source_ingestion_intents)")
            }:
                connection.execute(
                    "ALTER TABLE source_ingestion_intents ADD COLUMN "
                    "lock_protocol_version INTEGER NOT NULL DEFAULT 0"
                )
            if "document_preexisted" not in {
                row[1] for row in connection.execute("PRAGMA table_info(source_ingestion_intents)")
            }:
                connection.execute(
                    "ALTER TABLE source_ingestion_intents ADD COLUMN "
                    "document_preexisted INTEGER NOT NULL DEFAULT 1"
                )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS source_deletion_intents("
                "source_id TEXT PRIMARY KEY, notebook_id TEXT NOT NULL, "
                "document_id TEXT NOT NULL, actor_id TEXT NOT NULL, "
                "token TEXT NOT NULL UNIQUE, state TEXT NOT NULL "
                "CHECK(state IN ('deleting','deleted')))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS source_ingestion_asset_candidates("
                "notebook_id TEXT NOT NULL, source_content_hash TEXT NOT NULL, "
                "asset_hash TEXT NOT NULL, mime_type TEXT NOT NULL, "
                "preexisting INTEGER NOT NULL CHECK(preexisting IN (0,1)), "
                "PRIMARY KEY(notebook_id,source_content_hash,asset_hash,mime_type))"
            )
            connection.execute(
                "INSERT OR IGNORE INTO notebook_acl_revisions(notebook_id, revision) "
                "SELECT notebook_id, 1 FROM notebook_grants"
            )
            connection.execute(
                "INSERT OR IGNORE INTO notebook_acl_revisions(notebook_id, revision) "
                "SELECT notebook_id, 1 FROM retired_notebook_ids"
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _advance_revision(connection: sqlite3.Connection, notebook_id: UUID) -> None:
        connection.execute(
            "INSERT INTO notebook_acl_revisions(notebook_id, revision) VALUES(?, 1) "
            "ON CONFLICT(notebook_id) DO UPDATE SET revision=revision+1",
            (str(notebook_id),),
        )

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
            if connection.execute(
                "SELECT 1 FROM notebook_create_intents WHERE notebook_id=?", (str(notebook_id),)
            ).fetchone():
                raise ValueError("pending notebook creation cannot receive ad hoc grants")
            connection.execute(
                "INSERT INTO notebook_grants(actor_id,notebook_id,role,granted_by,status) "
                "VALUES(?,?,?,?,'active')",
                (str(actor_id), str(notebook_id), role, str(operator_id)),
            )
            self._advance_revision(connection, notebook_id)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _require_live_owner(
        connection: sqlite3.Connection, *, operator_id: UUID, notebook_id: UUID
    ) -> None:
        """Check the operator inside the transaction that changes the ACL."""
        notebook = str(notebook_id)
        if (
            connection.execute(
                "SELECT 1 FROM retired_notebook_ids WHERE notebook_id=? "
                "UNION SELECT 1 FROM notebook_create_intents WHERE notebook_id=?",
                (notebook, notebook),
            ).fetchone()
            or not connection.execute(
                "SELECT 1 FROM notebook_grants WHERE actor_id=? AND notebook_id=? "
                "AND role='owner' AND status='active'",
                (str(operator_id), notebook),
            ).fetchone()
        ):
            raise NotFoundError("authorized resource was not found")

    @contextmanager
    def owner_write_lease(self, *, actor_id: UUID, notebook_id: UUID) -> Iterator[int]:
        """Hold the ACL writer lock while one authorized notebook-store write runs.

        This serializes grant/revoke/retire with the write, but it does not
        create a cross-store transaction. A crashed writer releases the lock;
        the notebook store's own transaction determines whether its write stuck.
        """
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        try:
            connection = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                row = connection.execute(
                    "SELECT revision FROM notebook_acl_revisions WHERE notebook_id=? "
                    "AND NOT EXISTS (SELECT 1 FROM source_ingestion_intents "
                    "WHERE notebook_id=? AND state NOT IN ('published','recoverable')) "
                    "AND NOT EXISTS (SELECT 1 FROM source_deletion_intents "
                    "WHERE notebook_id=? AND state='deleting')",
                    (str(notebook_id), str(notebook_id), str(notebook_id)),
                ).fetchone()
            except sqlite3.DatabaseError as error:
                raise DependencyUnavailableError("membership authority is unavailable") from error
            if row is None or not isinstance(row[0], int) or row[0] < 1:
                raise NotFoundError("authorized resource was not found")
            yield row[0]
            try:
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
            except sqlite3.DatabaseError as error:
                raise DependencyUnavailableError("membership authority is unavailable") from error
        finally:
            connection.rollback()
            connection.close()

    @contextmanager
    def source_ingestion_process_lock(self) -> Iterator[object]:
        """Serialize source artifact writers and recovery across processes.

        The lock lives in a distinct SQLite file, so ACL revocation does not
        wait for parsing or embedding. A killed process releases the SQLite
        transaction; a live writer prevents recovery from acquiring it.
        """
        if not self.path.is_file() or not self._source_lock_path.is_file():
            raise DependencyUnavailableError("source operation coordination is unavailable")
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self._source_lock_path.as_uri() + "?mode=rw",
                uri=True,
                timeout=0,
                isolation_level=None,
            )
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.DatabaseError as error:
            if connection is not None:
                connection.close()
            raise DependencyUnavailableError(
                "source operation coordination is unavailable"
            ) from error
        assert connection is not None
        lease = object()
        self._active_source_leases[lease] = connection
        try:
            yield lease
        finally:
            self._active_source_leases.pop(lease, None)
            connection.rollback()
            connection.close()

    def _require_source_process_lease(self, lease: object | None) -> None:
        connection = self._active_source_leases.get(lease)
        if connection is None or not connection.in_transaction:
            raise DependencyUnavailableError("source operation coordination is unavailable")

    def reserve_source_ingestion(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        content_hash: str,
        token: UUID,
        document_preexisted: bool = True,
        process_lease: object | None = None,
    ) -> int:
        """Durably quarantine a notebook before any multi-store source write.

        A duplicate or interrupted intent is never silently restarted. A
        privileged reconciliation must inspect its artifacts first.
        """
        if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
            raise ValueError("source content hash must be lowercase SHA-256")
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        if process_lease is not None:
            self._require_source_process_lease(process_lease)
        protocol_version = 1 if process_lease is not None else 0
        try:
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                pending = connection.execute(
                    "SELECT 1 FROM source_ingestion_intents WHERE "
                    "(notebook_id=? OR content_hash=?) "
                    "AND state NOT IN ('published','recoverable')",
                    (str(notebook_id), content_hash),
                ).fetchone()
                if pending is not None:
                    raise DependencyUnavailableError(
                        "source ingestion requires reconciliation", retryable=False
                    )
                prior = connection.execute(
                    "SELECT 1 FROM source_ingestion_intents WHERE notebook_id=? AND content_hash=?",
                    (str(notebook_id), content_hash),
                ).fetchone()
                if prior is None:
                    connection.execute(
                        "INSERT INTO source_ingestion_intents"
                        "(notebook_id,content_hash,actor_id,token,state,lock_protocol_version,"
                        "document_preexisted) VALUES(?,?,?,?,'incomplete',?,?)",
                        (
                            str(notebook_id),
                            content_hash,
                            str(actor_id),
                            str(token),
                            protocol_version,
                            int(document_preexisted),
                        ),
                    )
                else:
                    connection.execute(
                        "UPDATE source_ingestion_intents SET actor_id=?,token=?,"
                        "state='incomplete',source_id=NULL,lock_protocol_version=?,"
                        "document_preexisted=? "
                        "WHERE notebook_id=? AND content_hash=? "
                        "AND state IN ('published','recoverable')",
                        (
                            str(actor_id),
                            str(token),
                            protocol_version,
                            int(document_preexisted),
                            str(notebook_id),
                            content_hash,
                        ),
                    )
                connection.execute(
                    "DELETE FROM source_ingestion_asset_candidates WHERE notebook_id=? "
                    "AND source_content_hash=?",
                    (str(notebook_id), content_hash),
                )
                self._advance_revision(connection, notebook_id)
                revision = connection.execute(
                    "SELECT revision FROM notebook_acl_revisions WHERE notebook_id=?",
                    (str(notebook_id),),
                ).fetchone()
                if revision is None:
                    raise DependencyUnavailableError("membership revision is unavailable")
                connection.commit()
                return int(revision[0])
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    def record_source_ingestion_asset_candidate(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        source_content_hash: str,
        token: UUID,
        asset_hash: str,
        mime_type: str,
        preexisting: bool,
        process_lease: object,
    ) -> None:
        """Record exact candidate identity before the first filesystem write."""
        self._require_source_process_lease(process_lease)
        if len(asset_hash) != 64 or any(char not in "0123456789abcdef" for char in asset_hash):
            raise ValueError("asset hash must be lowercase SHA-256")
        try:
            with closing(sqlite3.connect(self.path, timeout=0, isolation_level=None)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                row = connection.execute(
                    "SELECT 1 FROM source_ingestion_intents WHERE notebook_id=? "
                    "AND content_hash=? AND actor_id=? AND token=? "
                    "AND state='incomplete' AND lock_protocol_version=1",
                    (str(notebook_id), source_content_hash, str(actor_id), str(token)),
                ).fetchone()
                if row is None:
                    raise NotFoundError("authorized resource was not found")
                # A second occurrence of the same bytes within this operation
                # cannot turn a newly created blob into a pre-existing one.
                prior_new = connection.execute(
                    "SELECT 1 FROM source_ingestion_asset_candidates WHERE "
                    "notebook_id=? AND source_content_hash=? AND asset_hash=? "
                    "AND preexisting=0",
                    (str(notebook_id), source_content_hash, asset_hash),
                ).fetchone()
                connection.execute(
                    "INSERT INTO source_ingestion_asset_candidates "
                    "(notebook_id,source_content_hash,asset_hash,mime_type,preexisting) "
                    "VALUES(?,?,?,?,?) ON CONFLICT DO UPDATE SET "
                    "preexisting=min(preexisting,excluded.preexisting)",
                    (
                        str(notebook_id),
                        source_content_hash,
                        asset_hash,
                        mime_type,
                        int(preexisting and prior_new is None),
                    ),
                )
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    def source_ingestion_asset_candidates(
        self, *, actor_id: UUID, notebook_id: UUID, content_hash: str
    ) -> tuple[tuple[str, str, bool], ...]:
        """Return only this owner's recorded candidates while recovery is quarantined."""
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                rows = connection.execute(
                    "SELECT asset_hash,mime_type,preexisting FROM "
                    "source_ingestion_asset_candidates WHERE notebook_id=? "
                    "AND source_content_hash=? ORDER BY asset_hash,mime_type",
                    (str(notebook_id), content_hash),
                ).fetchall()
                return tuple((str(row[0]), str(row[1]), bool(row[2])) for row in rows)
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    def source_ingestion_document_preexisted(
        self, *, actor_id: UUID, notebook_id: UUID, content_hash: str
    ) -> bool:
        """Old intents default to preservation, never an inferred ownership claim."""
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                row = connection.execute(
                    "SELECT document_preexisted FROM source_ingestion_intents "
                    "WHERE notebook_id=? AND content_hash=?",
                    (str(notebook_id), content_hash),
                ).fetchone()
                if row is None or row[0] not in (0, 1):
                    raise DependencyUnavailableError("source origin record is unavailable")
                return bool(row[0])
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    @contextmanager
    def source_ingestion_write_lease(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        content_hash: str,
        token: UUID,
        reserved_revision: int,
        process_lease: object | None = None,
    ) -> Iterator[Callable[[UUID], None]]:
        """Serialize publication with ACL changes; keep crash state quarantined.

        The intent was committed separately before any artifact write. The
        lease commits `published` only after the caller's complete multi-store
        operation returns. A crash or exception leaves an incomplete intent.
        """
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        source_id: UUID | None = None

        def record_source(selected: UUID) -> None:
            nonlocal source_id
            if source_id is not None:
                raise ValueError("source publication is already recorded")
            source_id = selected

        try:
            connection = sqlite3.connect(self.path, timeout=0, isolation_level=None)
            connection.execute("BEGIN IMMEDIATE")
            self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
            row = connection.execute(
                "SELECT i.actor_id,i.token,i.state,r.revision,i.lock_protocol_version "
                "FROM source_ingestion_intents i "
                "JOIN notebook_acl_revisions r ON r.notebook_id=i.notebook_id "
                "WHERE i.notebook_id=? AND i.content_hash=?",
                (str(notebook_id), content_hash),
            ).fetchone()
            if row is None:
                raise NotFoundError("authorized resource was not found")
            if row[4] == 1:
                self._require_source_process_lease(process_lease)
            if row[:4] != (str(actor_id), str(token), "incomplete", reserved_revision):
                raise NotFoundError("authorized resource was not found")
            yield record_source
            if source_id is None:
                raise DependencyUnavailableError("source association was not published")
            self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
            updated = connection.execute(
                "UPDATE source_ingestion_intents SET state='published',source_id=? "
                "WHERE notebook_id=? AND content_hash=? AND actor_id=? AND token=? "
                "AND state='incomplete'",
                (str(source_id), str(notebook_id), content_hash, str(actor_id), str(token)),
            ).rowcount
            if updated != 1:
                raise NotFoundError("authorized resource was not found")
            connection.execute(
                "DELETE FROM source_ingestion_asset_candidates WHERE notebook_id=? "
                "AND source_content_hash=?",
                (str(notebook_id), content_hash),
            )
            self._advance_revision(connection, notebook_id)
            connection.commit()
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error
        finally:
            if "connection" in locals():
                connection.rollback()
                connection.close()

    def source_ingestion_state(self, notebook_id: UUID, content_hash: str) -> str | None:
        """Read-only recovery evidence; absence is not a publication proof."""
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                row = connection.execute(
                    "SELECT state FROM source_ingestion_intents WHERE notebook_id=? "
                    "AND content_hash=?",
                    (str(notebook_id), content_hash),
                ).fetchone()
                return str(row[0]) if row is not None else None
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    def unresolved_source_ingestion_intents(self) -> tuple[tuple[UUID, UUID, str, str], ...]:
        """Inventory quarantining intents for a recovery operator, never as grants."""
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                rows = connection.execute(
                    "SELECT notebook_id,actor_id,content_hash,state "
                    "FROM source_ingestion_intents "
                    "WHERE state NOT IN ('published','recoverable') "
                    "ORDER BY notebook_id,content_hash"
                ).fetchall()
            result = tuple((UUID(row[0]), UUID(row[1]), str(row[2]), str(row[3])) for row in rows)
            if any(
                len(content_hash) != 64
                or any(char not in "0123456789abcdef" for char in content_hash)
                for _, _, content_hash, _ in result
            ):
                raise ValueError("source recovery intent has an invalid content hash")
            return result
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise DependencyUnavailableError("membership recovery census is unavailable") from error

    def reserve_source_deletion(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        source_id: UUID,
        document_id: UUID,
        token: UUID,
        process_lease: object,
    ) -> None:
        """Quarantine a source before a cross-store deletion begins."""
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        self._require_source_process_lease(process_lease)
        try:
            with closing(sqlite3.connect(self.path, timeout=0, isolation_level=None)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                pending = connection.execute(
                    "SELECT 1 FROM source_ingestion_intents WHERE notebook_id=? "
                    "AND state NOT IN ('published','recoverable') UNION SELECT 1 "
                    "FROM source_deletion_intents WHERE notebook_id=? AND state='deleting'",
                    (str(notebook_id), str(notebook_id)),
                ).fetchone()
                if pending is not None:
                    raise DependencyUnavailableError("source operation requires reconciliation")
                prior = connection.execute(
                    "SELECT notebook_id,document_id,state FROM source_deletion_intents "
                    "WHERE source_id=?",
                    (str(source_id),),
                ).fetchone()
                if prior is not None and prior != (str(notebook_id), str(document_id), "deleted"):
                    raise NotFoundError("authorized resource was not found")
                if prior is None:
                    connection.execute(
                        "INSERT INTO source_deletion_intents "
                        "(source_id,notebook_id,document_id,actor_id,token,state) "
                        "VALUES(?,?,?,?,?,'deleting')",
                        (
                            str(source_id),
                            str(notebook_id),
                            str(document_id),
                            str(actor_id),
                            str(token),
                        ),
                    )
                else:
                    connection.execute(
                        "UPDATE source_deletion_intents SET actor_id=?,token=?,state='deleting' "
                        "WHERE source_id=?",
                        (str(actor_id), str(token), str(source_id)),
                    )
                self._advance_revision(connection, notebook_id)
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    @contextmanager
    def source_deletion_completion_lease(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        source_id: UUID,
        process_lease: object,
    ) -> Iterator[tuple[UUID, bool]]:
        """Complete or recover a pending delete under the ACL writer lock."""
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        self._require_source_process_lease(process_lease)
        try:
            with closing(sqlite3.connect(self.path, timeout=0, isolation_level=None)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                row = connection.execute(
                    "SELECT document_id,state FROM source_deletion_intents WHERE source_id=? "
                    "AND notebook_id=? AND state IN ('deleting','deleted')",
                    (str(source_id), str(notebook_id)),
                ).fetchone()
                if row is None:
                    raise NotFoundError("authorized resource was not found")
                document_id = UUID(row[0])
                if row[1] == "deleted":
                    yield document_id, False
                    return
                yield document_id, True
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                updated = connection.execute(
                    "UPDATE source_deletion_intents SET state='deleted' WHERE source_id=? "
                    "AND notebook_id=? AND state='deleting'",
                    (str(source_id), str(notebook_id)),
                ).rowcount
                if updated != 1:
                    raise NotFoundError("authorized resource was not found")
                self._advance_revision(connection, notebook_id)
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    def mark_source_ingestion_failed(
        self, *, notebook_id: UUID, content_hash: str, token: UUID
    ) -> None:
        """Record an observed failure without ever releasing quarantine."""
        if not self.path.is_file():
            return
        try:
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE source_ingestion_intents SET state='failed' "
                    "WHERE notebook_id=? AND content_hash=? AND token=? AND state='incomplete'",
                    (str(notebook_id), content_hash, str(token)),
                )
                connection.commit()
        except sqlite3.DatabaseError:
            # The durable incomplete intent still blocks serving on outage.
            return

    @contextmanager
    def source_ingestion_recovery_lease(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        content_hash: str,
        process_lease: object | None = None,
    ) -> Iterator[tuple[bool, Callable[[], None]]]:
        """Hold the ACL writer lock while canonical source links are removed.

        The caller must reproject membership and verify that no source link
        remains before this context exits. On crash or failure, the intent
        stays quarantined and a new recovery attempt may repeat the work.
        """
        if not self.path.is_file():
            raise DependencyUnavailableError("membership authority is unavailable")
        reconciled = False

        def record_reconciled() -> None:
            nonlocal reconciled
            reconciled = True

        try:
            with closing(sqlite3.connect(self.path, timeout=0, isolation_level=None)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                row = connection.execute(
                    "SELECT state,lock_protocol_version FROM source_ingestion_intents "
                    "WHERE notebook_id=? AND content_hash=?",
                    (str(notebook_id), content_hash),
                ).fetchone()
                if row is None or row[0] not in {
                    "incomplete",
                    "failed",
                    "quarantined",
                    "recoverable",
                }:
                    raise NotFoundError("authorized resource was not found")
                if row[1] == 1:
                    self._require_source_process_lease(process_lease)
                elif row[0] == "incomplete":
                    # An old intent has no proof that its writer was locked.
                    raise NotFoundError("authorized resource was not found")
                if row[0] == "recoverable":
                    yield False, record_reconciled
                    return
                yield True, record_reconciled
                if not reconciled:
                    raise DependencyUnavailableError("source reconciliation was not verified")
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                updated = connection.execute(
                    "UPDATE source_ingestion_intents SET state='recoverable',source_id=NULL "
                    "WHERE notebook_id=? AND content_hash=? AND state IN "
                    "('incomplete','failed','quarantined')",
                    (str(notebook_id), content_hash),
                ).rowcount
                if updated != 1:
                    raise NotFoundError("authorized resource was not found")
                connection.execute(
                    "DELETE FROM source_ingestion_asset_candidates WHERE notebook_id=? "
                    "AND source_content_hash=?",
                    (str(notebook_id), content_hash),
                )
                self._advance_revision(connection, notebook_id)
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    def bind_final_qa_v1_execution(
        self,
        *,
        assistant_turn_id: UUID,
        actor_id: UUID,
        notebook_id: UUID,
        session_id: UUID,
        user_turn_id: UUID,
        acl_revision: int,
    ) -> None:
        """Claim a V1 publication slot for one live owner and ACL revision.

        Old execution rows without this independently durable binding are not
        admitted to the ACL-enabled replay path. This is not a cross-store
        transaction; an orphaned binding is safe to retry only with identical
        authority context and otherwise remains quarantined.
        """
        if not self.path.is_file() or acl_revision < 1:
            raise DependencyUnavailableError("membership authority is unavailable")
        expected = (
            str(actor_id),
            str(notebook_id),
            str(session_id),
            str(user_turn_id),
            acl_revision,
        )
        try:
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                revision = connection.execute(
                    "SELECT revision FROM notebook_acl_revisions WHERE notebook_id=?",
                    (str(notebook_id),),
                ).fetchone()
                if revision != (acl_revision,):
                    raise NotFoundError("authorized resource was not found")
                existing = connection.execute(
                    "SELECT actor_id,notebook_id,session_id,user_turn_id,acl_revision "
                    "FROM final_qa_v1_acl_bindings WHERE assistant_turn_id=?",
                    (str(assistant_turn_id),),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO final_qa_v1_acl_bindings"
                        "(assistant_turn_id,actor_id,notebook_id,session_id,"
                        "user_turn_id,acl_revision) "
                        "VALUES(?,?,?,?,?,?)",
                        (str(assistant_turn_id), *expected),
                    )
                elif existing != expected:
                    raise NotFoundError("authorized resource was not found")
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    def verify_final_qa_v1_execution(
        self,
        *,
        assistant_turn_id: UUID,
        actor_id: UUID,
        notebook_id: UUID,
        session_id: UUID,
        user_turn_id: UUID,
        acl_revision: int,
        require_documents: bool = False,
    ) -> tuple[tuple[UUID, UUID], ...] | None:
        """Fail closed for an unbound, revoked, or revision-stale V1 replay."""
        if not self.path.is_file() or acl_revision < 1:
            raise DependencyUnavailableError("membership authority is unavailable")
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                row = connection.execute(
                    "SELECT b.actor_id,b.notebook_id,b.session_id,b.user_turn_id,b.acl_revision,"
                    "r.revision,b.document_scopes FROM final_qa_v1_acl_bindings b "
                    "JOIN notebook_acl_revisions r ON r.notebook_id=b.notebook_id "
                    "WHERE b.assistant_turn_id=?",
                    (str(assistant_turn_id),),
                ).fetchone()
                if row is None or row[:6] != (
                    str(actor_id),
                    str(notebook_id),
                    str(session_id),
                    str(user_turn_id),
                    acl_revision,
                    acl_revision,
                ):
                    raise NotFoundError("authorized resource was not found")
                if row[6] is None:
                    if require_documents:
                        raise NotFoundError("authorized resource was not found")
                    return None
                decoded = json.loads(row[6])
                if not isinstance(decoded, list) or any(
                    not isinstance(pair, list)
                    or len(pair) != 2
                    or any(not isinstance(value, str) for value in pair)
                    for pair in decoded
                ):
                    raise ValueError("invalid FinalQA document binding")
                documents = tuple((UUID(pair[0]), UUID(pair[1])) for pair in decoded)
                if documents != tuple(sorted(set(documents))):
                    raise ValueError("invalid FinalQA document binding")
                return documents
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    def bind_final_qa_v1_documents(
        self,
        *,
        assistant_turn_id: UUID,
        actor_id: UUID,
        notebook_id: UUID,
        session_id: UUID,
        user_turn_id: UUID,
        acl_revision: int,
        documents: tuple[tuple[UUID, UUID], ...],
    ) -> None:
        """Durably bind the exact authorized fusion ancestry before publication."""
        if documents != tuple(sorted(set(documents))):
            raise ValueError("document scope identities must be sorted and unique")
        self.verify_final_qa_v1_execution(
            assistant_turn_id=assistant_turn_id,
            actor_id=actor_id,
            notebook_id=notebook_id,
            session_id=session_id,
            user_turn_id=user_turn_id,
            acl_revision=acl_revision,
        )
        encoded = json.dumps([[str(doc), str(version)] for doc, version in documents])
        try:
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._require_live_owner(connection, operator_id=actor_id, notebook_id=notebook_id)
                row = connection.execute(
                    "SELECT b.actor_id,b.notebook_id,b.session_id,b.user_turn_id,b.acl_revision,"
                    "r.revision,b.document_scopes FROM final_qa_v1_acl_bindings b "
                    "JOIN notebook_acl_revisions r ON r.notebook_id=b.notebook_id "
                    "WHERE b.assistant_turn_id=?",
                    (str(assistant_turn_id),),
                ).fetchone()
                if row is None or row[:6] != (
                    str(actor_id),
                    str(notebook_id),
                    str(session_id),
                    str(user_turn_id),
                    acl_revision,
                    acl_revision,
                ):
                    raise NotFoundError("authorized resource was not found")
                if row[6] is None:
                    connection.execute(
                        "UPDATE final_qa_v1_acl_bindings SET document_scopes=? "
                        "WHERE assistant_turn_id=?",
                        (encoded, str(assistant_turn_id)),
                    )
                elif row[6] != encoded:
                    raise NotFoundError("authorized resource was not found")
                connection.commit()
        except sqlite3.DatabaseError as error:
            raise DependencyUnavailableError("membership authority is unavailable") from error

    def grant_reader_as_owner(
        self, *, operator_id: UUID, notebook_id: UUID, reader_id: UUID
    ) -> None:
        """Serialize owner authorization and the reader grant in one ACL transaction."""
        if not self.path.is_file():
            raise NotFoundError("authorized resource was not found")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_live_owner(connection, operator_id=operator_id, notebook_id=notebook_id)
            if reader_id == operator_id:
                raise ValueError("owner cannot grant a second role to self")
            connection.execute(
                "INSERT INTO notebook_grants(actor_id,notebook_id,role,granted_by,status) "
                "VALUES(?,?, 'reader',?,'active')",
                (str(reader_id), str(notebook_id), str(operator_id)),
            )
            self._advance_revision(connection, notebook_id)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def revoke_reader_as_owner(
        self, *, operator_id: UUID, notebook_id: UUID, reader_id: UUID
    ) -> None:
        """Serialize owner authorization and revocation; never revoke an owner."""
        if not self.path.is_file():
            raise NotFoundError("authorized resource was not found")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_live_owner(connection, operator_id=operator_id, notebook_id=notebook_id)
            deleted = connection.execute(
                "DELETE FROM notebook_grants WHERE actor_id=? AND notebook_id=? "
                "AND role='reader' AND status='active'",
                (str(reader_id), str(notebook_id)),
            ).rowcount
            if not deleted:
                raise NotFoundError("authorized resource was not found")
            self._advance_revision(connection, notebook_id)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _encode_notebook(notebook: Notebook) -> str:
        return json.dumps(
            {
                "notebook_id": str(notebook.notebook_id),
                "title": notebook.title,
                "description": notebook.description,
                "created_at": notebook.created_at.isoformat(),
                "updated_at": notebook.updated_at.isoformat(),
                "metadata": thaw_json(notebook.metadata),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _decode_notebook(payload: str) -> Notebook:
        data = json.loads(payload)
        return Notebook(
            notebook_id=UUID(data["notebook_id"]),
            title=data["title"],
            description=data["description"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=FrozenMetadata(data["metadata"]),
        )

    def reserve_create(
        self, *, notebook_id: UUID, actor_id: UUID, token: UUID, notebook: Notebook | None = None
    ) -> None:
        """Durably bind a new notebook identity to one actor before storage writes."""
        if notebook is not None and notebook.notebook_id != notebook_id:
            raise ValueError("notebook payload identity mismatch")
        payload = self._encode_notebook(notebook) if notebook is not None else None
        if not self.path.is_file():
            raise RuntimeError("scope authority has not been initialized")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT actor_id, token, payload FROM notebook_create_intents WHERE notebook_id=?",
                (str(notebook_id),),
            ).fetchone()
            if existing is not None:
                if existing != (str(actor_id), str(token), payload):
                    raise ValueError("conflicting notebook creation intent")
            else:
                if connection.execute(
                    "SELECT 1 FROM retired_notebook_ids WHERE notebook_id=? "
                    "UNION SELECT 1 FROM notebook_acl_revisions WHERE notebook_id=?",
                    (str(notebook_id), str(notebook_id)),
                ).fetchone():
                    raise ValueError("notebook identity is not fresh")
                connection.execute(
                    "INSERT INTO notebook_create_intents(notebook_id, actor_id, token, payload) "
                    "VALUES(?,?,?,?)",
                    (str(notebook_id), str(actor_id), str(token), payload),
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def pending_create(self, notebook_id: UUID) -> tuple[UUID, UUID] | None:
        """Read-only recovery lookup; a pending row grants no access."""
        if not self.path.is_file():
            return None
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                row = connection.execute(
                    "SELECT actor_id, token FROM notebook_create_intents WHERE notebook_id=?",
                    (str(notebook_id),),
                ).fetchone()
                return (UUID(row[0]), UUID(row[1])) if row is not None else None
        except (sqlite3.DatabaseError, ValueError):
            return None

    def pending_create_record(self, notebook_id: UUID) -> tuple[UUID, UUID, Notebook] | None:
        """Return only complete, valid intent data; legacy intents stay quarantined."""
        if not self.path.is_file():
            return None
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                row = connection.execute(
                    "SELECT actor_id, token, payload FROM notebook_create_intents "
                    "WHERE notebook_id=?",
                    (str(notebook_id),),
                ).fetchone()
                if row is None or row[2] is None:
                    return None
                notebook = self._decode_notebook(row[2])
                if notebook.notebook_id != notebook_id:
                    return None
                return UUID(row[0]), UUID(row[1]), notebook
        except (sqlite3.DatabaseError, ValueError, TypeError, KeyError, AttributeError):
            return None

    def finish_create(self, *, notebook_id: UUID, actor_id: UUID, token: UUID) -> None:
        """Activate the reserved owner only after notebook storage is verified."""
        if not self.path.is_file():
            raise RuntimeError("scope authority has not been initialized")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            completed = connection.execute(
                "SELECT actor_id, token FROM notebook_create_completions WHERE notebook_id=?",
                (str(notebook_id),),
            ).fetchone()
            if completed == (str(actor_id), str(token)):
                if (
                    connection.execute(
                        "SELECT 1 FROM notebook_grants WHERE actor_id=? AND notebook_id=? "
                        "AND role='owner' AND status='active'",
                        (str(actor_id), str(notebook_id)),
                    ).fetchone()
                    is None
                ):
                    raise ValueError("completed notebook owner is no longer active")
                connection.commit()
                return
            if connection.execute(
                "SELECT actor_id, token FROM notebook_create_intents WHERE notebook_id=?",
                (str(notebook_id),),
            ).fetchone() != (str(actor_id), str(token)):
                raise ValueError("notebook creation intent is unavailable or mismatched")
            connection.execute(
                "INSERT INTO notebook_grants(actor_id,notebook_id,role,granted_by,status) "
                "VALUES(?,?,'owner',?,'active')",
                (str(actor_id), str(notebook_id), str(actor_id)),
            )
            self._advance_revision(connection, notebook_id)
            connection.execute(
                "DELETE FROM notebook_create_intents WHERE notebook_id=?", (str(notebook_id),)
            )
            connection.execute(
                "INSERT INTO notebook_create_completions(notebook_id, actor_id, token) "
                "VALUES(?,?,?)",
                (str(notebook_id), str(actor_id), str(token)),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def completed_create(self, notebook_id: UUID) -> tuple[UUID, UUID] | None:
        if not self.path.is_file():
            return None
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                if connection.execute(
                    "SELECT 1 FROM retired_notebook_ids WHERE notebook_id=?", (str(notebook_id),)
                ).fetchone():
                    return None
                row = connection.execute(
                    "SELECT actor_id, token FROM notebook_create_completions WHERE notebook_id=?",
                    (str(notebook_id),),
                ).fetchone()
                return (UUID(row[0]), UUID(row[1])) if row is not None else None
        except (sqlite3.DatabaseError, ValueError):
            return None

    def revoke(self, *, actor_id: UUID, notebook_id: UUID) -> None:
        """Revoke one actor without disturbing another notebook's grants."""
        if not self.path.is_file():
            raise RuntimeError("scope authority has not been initialized")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            deleted = connection.execute(
                "DELETE FROM notebook_grants WHERE actor_id=? AND notebook_id=?",
                (str(actor_id), str(notebook_id)),
            ).rowcount
            if deleted:
                self._advance_revision(connection, notebook_id)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def revision(self, notebook_id: UUID) -> int | None:
        """Current revision for cursor binding; absence is never authority."""
        if not self.path.is_file():
            return None
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                row = connection.execute(
                    "SELECT revision FROM notebook_acl_revisions WHERE notebook_id=? "
                    "AND NOT EXISTS (SELECT 1 FROM source_ingestion_intents "
                    "WHERE notebook_id=? AND state NOT IN ('published','recoverable')) "
                    "AND NOT EXISTS (SELECT 1 FROM source_deletion_intents "
                    "WHERE notebook_id=? AND state='deleting')",
                    (str(notebook_id), str(notebook_id), str(notebook_id)),
                ).fetchone()
                return int(row[0]) if row is not None else None
        except sqlite3.DatabaseError:
            return None

    def authorized_notebook_ids(self, actor_id: UUID) -> tuple[UUID, ...]:
        """Discover only active explicit memberships; outage returns no scope."""
        if not self.path.is_file():
            return ()
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                rows = connection.execute(
                    "SELECT g.notebook_id FROM notebook_grants AS g "
                    "LEFT JOIN retired_notebook_ids AS r ON r.notebook_id=g.notebook_id "
                    "WHERE g.actor_id=? AND g.status='active' AND r.notebook_id IS NULL "
                    "AND NOT EXISTS (SELECT 1 FROM source_ingestion_intents AS i "
                    "WHERE i.notebook_id=g.notebook_id "
                    "AND i.state NOT IN ('published','recoverable')) "
                    "AND NOT EXISTS (SELECT 1 FROM source_deletion_intents AS d "
                    "WHERE d.notebook_id=g.notebook_id AND d.state='deleting') "
                    "ORDER BY g.notebook_id",
                    (str(actor_id),),
                ).fetchall()
                return tuple(UUID(row[0]) for row in rows)
        except (sqlite3.DatabaseError, ValueError):
            return ()

    def active_role(self, actor_id: UUID, notebook_id: UUID) -> str | None:
        """Return an explicit live role; never infer one from notebook storage."""
        if not self.path.is_file():
            return None
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
                if connection.execute(
                    "SELECT 1 FROM retired_notebook_ids WHERE notebook_id=? "
                    "UNION SELECT 1 FROM source_ingestion_intents "
                    "WHERE notebook_id=? AND state NOT IN ('published','recoverable') "
                    "UNION SELECT 1 FROM source_deletion_intents "
                    "WHERE notebook_id=? AND state='deleting'",
                    (str(notebook_id), str(notebook_id), str(notebook_id)),
                ).fetchone():
                    return None
                row = connection.execute(
                    "SELECT role FROM notebook_grants WHERE actor_id=? AND notebook_id=? "
                    "AND status='active'",
                    (str(actor_id), str(notebook_id)),
                ).fetchone()
                return str(row[0]) if row is not None else None
        except sqlite3.DatabaseError:
            return None

    def retire_notebook(self, notebook_id: UUID, *, operator_id: UUID | None = None) -> None:
        """Permanently invalidate grants for a deleted notebook identity.

        Call before deleting notebook storage: an interrupted deletion then
        fails closed rather than leaving usable stale grants. Public deletion
        supplies the trusted operator so ownership is checked in this same ACL
        transaction. Operator-less calls are restricted to idempotent recovery
        of an already-tombstoned identity, never first-time deletion.
        """
        if not self.path.is_file():
            raise RuntimeError("scope authority has not been initialized")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            if operator_id is not None:
                self._require_live_owner(
                    connection, operator_id=operator_id, notebook_id=notebook_id
                )
            elif (
                connection.execute(
                    "SELECT 1 FROM retired_notebook_ids WHERE notebook_id=?",
                    (str(notebook_id),),
                ).fetchone()
                is None
            ):
                raise NotFoundError("authorized resource was not found")
            inserted = connection.execute(
                "INSERT OR IGNORE INTO retired_notebook_ids(notebook_id) VALUES(?)",
                (str(notebook_id),),
            ).rowcount
            deleted = connection.execute(
                "DELETE FROM notebook_grants WHERE notebook_id=?", (str(notebook_id),)
            ).rowcount
            pending = connection.execute(
                "DELETE FROM notebook_create_intents WHERE notebook_id=?", (str(notebook_id),)
            ).rowcount
            completed = connection.execute(
                "DELETE FROM notebook_create_completions WHERE notebook_id=?",
                (str(notebook_id),),
            ).rowcount
            if inserted or deleted or pending or completed:
                self._advance_revision(connection, notebook_id)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def permits(self, actor_id: UUID, notebook_id: UUID, *, operation: str = "read") -> bool:
        if operation not in {"read", "write"}:
            return False
        if not self.path.is_file():
            return False
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        try:
            if (
                connection.execute(
                    "SELECT 1 FROM retired_notebook_ids WHERE notebook_id=? "
                    "UNION SELECT 1 FROM source_ingestion_intents "
                    "WHERE notebook_id=? AND state NOT IN ('published','recoverable') "
                    "UNION SELECT 1 FROM source_deletion_intents "
                    "WHERE notebook_id=? AND state='deleting'",
                    (str(notebook_id), str(notebook_id), str(notebook_id)),
                ).fetchone()
                is not None
            ):
                return False
            row = connection.execute(
                "SELECT 1 FROM notebook_grants WHERE actor_id=? AND notebook_id=? "
                "AND status='active' AND (?='read' OR role='owner')",
                (str(actor_id), str(notebook_id), operation),
            ).fetchone()
            return row is not None
        except sqlite3.DatabaseError:
            return False
        finally:
            connection.close()
