"""Add blocked_rules table for web control plane read/write paths.

Chunk 1 defines this as an idempotent, fresh-schema additive migration.
"""

from __future__ import annotations

import sqlite3

SQL = """
CREATE TABLE IF NOT EXISTS blocked_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('filename', 'regex')),
    reason TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def apply(conn: sqlite3.Connection) -> None:
    """Apply blocked_rules migration idempotently."""

    conn.executescript(SQL)
    conn.commit()
