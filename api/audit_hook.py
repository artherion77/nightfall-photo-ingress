"""Audit utilities for API mutation flows."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import sqlite3


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def write_triage_requested_event(
    conn: sqlite3.Connection,
    *,
    action: str,
    item_id: str,
    actor: str,
    reason: str | None,
) -> None:
    """Write a durable pre-mutation audit event."""

    details = json.dumps({"item_id": item_id, "phase": "pre"})
    conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, NULL, ?, ?, ?, ?, ?)
        """,
        (item_id, f"triage_{action}_requested", reason, details, actor, _utc_now_iso()),
    )



def write_triage_compensating_event(
    conn: sqlite3.Connection,
    *,
    action: str,
    item_id: str,
    actor: str,
    reason: str | None,
) -> None:
    """Write a compensating audit event after failed mutation rollback."""

    compensating_details = json.dumps({"item_id": item_id, "phase": "compensating"})
    conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, NULL, ?, ?, ?, ?, ?)
        """,
        (item_id, f"triage_{action}_compensating", reason, compensating_details, actor, _utc_now_iso()),
    )