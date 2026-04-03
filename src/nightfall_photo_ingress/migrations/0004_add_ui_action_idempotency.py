"""Add ui_action_idempotency table for API mutation replay safety.

Chunk 1 defines this as an idempotent, fresh-schema additive migration.
"""

from __future__ import annotations

import sqlite3

SQL = """
CREATE TABLE IF NOT EXISTS ui_action_idempotency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL,
    item_id TEXT NOT NULL,
    request_body_json TEXT,
    response_status INTEGER NOT NULL,
    response_body_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


def apply(conn: sqlite3.Connection) -> None:
    """Apply ui_action_idempotency migration idempotently."""

    conn.executescript(SQL)
    conn.commit()
