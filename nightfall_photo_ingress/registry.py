"""SQLite registry and migration engine for Module 2.

This module provides a transaction-safe system-of-record for ingest state,
acceptance history, and immutable audit logging.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

LATEST_SCHEMA_VERSION = 1
ALLOWED_FILE_STATUSES = {"accepted", "rejected", "purged"}


class RegistryError(RuntimeError):
    """Raised when registry operations fail."""


@dataclass(frozen=True)
class FileRecord:
    """Typed view over one row in the files table."""

    sha256: str
    size_bytes: int
    status: str
    original_filename: str | None
    current_path: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class AuditRecord:
    """Typed view over one row in the audit log."""

    id: int
    sha256: str
    action: str
    reason: str | None
    actor: str
    ts: str


class Registry:
    """High-level API for schema migration and state transitions."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    @property
    def db_path(self) -> Path:
        """Expose the resolved database path."""

        return self._db_path

    def initialize(self) -> None:
        """Create parent directories, initialize schema, and run migrations."""

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            _set_pragmas(conn)
            _run_migrations(conn)

    def create_or_update_file(
        self,
        *,
        sha256: str,
        size_bytes: int,
        status: str,
        original_filename: str | None = None,
        current_path: str | None = None,
    ) -> None:
        """Insert or update a file record while preserving original timestamps."""

        self._validate_status(status)
        now = _utc_now()
        with self._connect() as conn:
            _set_pragmas(conn)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO files (
                    sha256,
                    size_bytes,
                    status,
                    original_filename,
                    current_path,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sha256) DO UPDATE SET
                    size_bytes = excluded.size_bytes,
                    status = excluded.status,
                    original_filename = COALESCE(excluded.original_filename, files.original_filename),
                    current_path = excluded.current_path,
                    updated_at = excluded.updated_at
                """,
                (sha256, size_bytes, status, original_filename, current_path, now, now),
            )
            conn.commit()

    def upsert_metadata_index(
        self,
        *,
        account: str,
        onedrive_id: str,
        size_bytes: int,
        modified_time: str,
        sha256: str,
    ) -> None:
        """Insert or update metadata pre-filter index entries."""

        now = _utc_now()
        with self._connect() as conn:
            _set_pragmas(conn)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO metadata_index (
                    account,
                    onedrive_id,
                    size_bytes,
                    modified_time,
                    sha256,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account, onedrive_id) DO UPDATE SET
                    size_bytes = excluded.size_bytes,
                    modified_time = excluded.modified_time,
                    sha256 = excluded.sha256,
                    updated_at = excluded.updated_at
                """,
                (account, onedrive_id, size_bytes, modified_time, sha256, now, now),
            )
            conn.commit()

    def upsert_file_origin(
        self,
        *,
        sha256: str,
        account: str,
        onedrive_id: str,
        path_hint: str | None,
    ) -> None:
        """Track account-to-file provenance for auditability."""

        now = _utc_now()
        with self._connect() as conn:
            _set_pragmas(conn)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO file_origins (
                    account,
                    onedrive_id,
                    sha256,
                    path_hint,
                    first_seen_at,
                    last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(account, onedrive_id) DO UPDATE SET
                    sha256 = excluded.sha256,
                    path_hint = excluded.path_hint,
                    last_seen_at = excluded.last_seen_at
                """,
                (account, onedrive_id, sha256, path_hint, now, now),
            )
            conn.commit()

    def record_acceptance(self, *, sha256: str, account: str, source_path: str) -> None:
        """Append acceptance history for files routed through accepted queue."""

        now = _utc_now()
        with self._connect() as conn:
            _set_pragmas(conn)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO accepted_records (
                    sha256,
                    account,
                    source_path,
                    accepted_at
                ) VALUES (?, ?, ?, ?)
                """,
                (sha256, account, source_path, now),
            )
            conn.commit()

    def clear_current_path(self, *, sha256: str) -> None:
        """Clear current_path when operators manually move files out of queue."""

        now = _utc_now()
        with self._connect() as conn:
            _set_pragmas(conn)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE files SET current_path = NULL, updated_at = ? WHERE sha256 = ?",
                (now, sha256),
            )
            conn.commit()

    def transition_status(
        self,
        *,
        sha256: str,
        new_status: str,
        reason: str,
        actor: str,
    ) -> None:
        """Transition status atomically and append immutable audit event."""

        self._validate_status(new_status)
        now = _utc_now()
        with self._connect() as conn:
            _set_pragmas(conn)
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute("SELECT sha256 FROM files WHERE sha256 = ?", (sha256,))
            if cursor.fetchone() is None:
                conn.rollback()
                raise RegistryError(f"Cannot transition missing sha256: {sha256}")

            conn.execute(
                "UPDATE files SET status = ?, updated_at = ? WHERE sha256 = ?",
                (new_status, now, sha256),
            )
            conn.execute(
                "INSERT INTO audit_log (sha256, action, reason, actor, ts) VALUES (?, ?, ?, ?, ?)",
                (sha256, new_status, reason, actor, now),
            )
            conn.commit()

    def append_audit_event(
        self,
        *,
        sha256: str,
        action: str,
        reason: str | None,
        actor: str,
    ) -> int:
        """Append one immutable event row and return its primary key."""

        now = _utc_now()
        with self._connect() as conn:
            _set_pragmas(conn)
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "INSERT INTO audit_log (sha256, action, reason, actor, ts) VALUES (?, ?, ?, ?, ?)",
                (sha256, action, reason, actor, now),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_file(self, *, sha256: str) -> FileRecord | None:
        """Return one file row by SHA-256 or None when missing."""

        with self._connect() as conn:
            _set_pragmas(conn)
            row = conn.execute(
                """
                SELECT sha256, size_bytes, status, original_filename, current_path, created_at, updated_at
                FROM files
                WHERE sha256 = ?
                """,
                (sha256,),
            ).fetchone()

        if row is None:
            return None
        return FileRecord(
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            status=row["status"],
            original_filename=row["original_filename"],
            current_path=row["current_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_audit_events(self, *, sha256: str) -> list[AuditRecord]:
        """Return immutable audit rows for one SHA-256 ordered by insertion."""

        with self._connect() as conn:
            _set_pragmas(conn)
            rows = conn.execute(
                "SELECT id, sha256, action, reason, actor, ts FROM audit_log WHERE sha256 = ? ORDER BY id ASC",
                (sha256,),
            ).fetchall()

        return [
            AuditRecord(
                id=row["id"],
                sha256=row["sha256"],
                action=row["action"],
                reason=row["reason"],
                actor=row["actor"],
                ts=row["ts"],
            )
            for row in rows
        ]

    def acceptance_count(self, *, sha256: str) -> int:
        """Return number of acceptance history entries for one SHA-256."""

        with self._connect() as conn:
            _set_pragmas(conn)
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM accepted_records WHERE sha256 = ?",
                (sha256,),
            ).fetchone()
        return int(row["n"]) if row is not None else 0

    def schema_version(self) -> int:
        """Return current SQLite user_version schema integer."""

        with self._connect() as conn:
            _set_pragmas(conn)
            row = conn.execute("PRAGMA user_version").fetchone()
        return int(row[0]) if row is not None else 0

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with row access by column names."""

        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _validate_status(value: str) -> None:
        """Reject unknown status values early to keep state clean."""

        if value not in ALLOWED_FILE_STATUSES:
            raise RegistryError(
                f"Invalid status '{value}', expected one of {sorted(ALLOWED_FILE_STATUSES)}"
            )


def _set_pragmas(conn: sqlite3.Connection) -> None:
    """Set connection-level SQLite pragmas used by registry operations."""

    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run schema migrations from current `user_version` to latest."""

    row = conn.execute("PRAGMA user_version").fetchone()
    current = int(row[0]) if row is not None else 0

    if current > LATEST_SCHEMA_VERSION:
        raise RegistryError(
            f"Database schema version {current} is newer than supported {LATEST_SCHEMA_VERSION}"
        )

    if current == 0:
        conn.executescript(_migration_v1_sql())
        conn.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION}")
        conn.commit()


def _migration_v1_sql() -> str:
    """Return SQL script for schema version 1."""

    return """
CREATE TABLE IF NOT EXISTS files (
    sha256 TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('accepted', 'rejected', 'purged')),
    original_filename TEXT,
    current_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata_index (
    account TEXT NOT NULL,
    onedrive_id TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    modified_time TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account, onedrive_id)
);

CREATE TABLE IF NOT EXISTS accepted_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL,
    account TEXT NOT NULL,
    source_path TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    FOREIGN KEY (sha256) REFERENCES files(sha256)
);

CREATE TABLE IF NOT EXISTS file_origins (
    account TEXT NOT NULL,
    onedrive_id TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    path_hint TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (account, onedrive_id),
    FOREIGN KEY (sha256) REFERENCES files(sha256)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    actor TEXT NOT NULL,
    ts TEXT NOT NULL,
    FOREIGN KEY (sha256) REFERENCES files(sha256)
);

CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(FAIL, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(FAIL, 'audit_log is append-only');
END;
"""


def _utc_now() -> str:
    """Return UTC timestamp in ISO-8601 format with timezone suffix."""

    return datetime.now(UTC).isoformat()
