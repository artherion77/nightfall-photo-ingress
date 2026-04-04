"""Audit-first hook utilities for API mutation flows."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
import sqlite3
from typing import Iterator


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def triage_audit_hook(
    conn: sqlite3.Connection,
    *,
    action: str,
    item_id: str,
    actor: str,
    reason: str | None,
) -> Iterator[None]:
    """Write pre-mutation audit and compensating event on failure."""

    details = json.dumps({"item_id": item_id, "phase": "pre"})
    conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, NULL, ?, ?, ?, ?, ?)
        """,
        (item_id, f"triage_{action}_requested", reason, details, actor, _utc_now_iso()),
    )

    try:
        yield
    except Exception:
        compensating_details = json.dumps({"item_id": item_id, "phase": "compensating"})
        conn.execute(
            """
            INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
            VALUES (?, NULL, ?, ?, ?, ?, ?)
            """,
            (item_id, f"triage_{action}_compensating", reason, compensating_details, actor, _utc_now_iso()),
        )
        raise