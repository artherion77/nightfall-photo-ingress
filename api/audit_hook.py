"""Audit utilities for API mutation flows."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import sqlite3


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def resolve_account_name(conn: sqlite3.Connection, item_id: str) -> str | None:
    """Resolve account name for a sha256 using available registry tables."""

    row = conn.execute(
        """
        SELECT account_name
        FROM metadata_index
        WHERE sha256 = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    if row and row[0]:
        return str(row[0])

    row = conn.execute(
        """
        SELECT account
        FROM file_origins
        WHERE sha256 = ?
        ORDER BY last_seen_at DESC
        LIMIT 1
        """,
        (item_id,),
    ).fetchone()
    if row and row[0]:
        return str(row[0])

    return None


def write_triage_requested_event(
    conn: sqlite3.Connection,
    *,
    action: str,
    item_id: str,
    actor: str,
    reason: str | None,
    client_ip: str | None = None,
) -> None:
    """Write a durable pre-mutation audit event."""

    payload = {"item_id": item_id, "phase": "pre"}
    if client_ip:
        payload["client_ip"] = client_ip
    details = json.dumps(payload)
    account_name = resolve_account_name(conn, item_id)
    conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, account_name, f"triage_{action}_requested", reason, details, actor, _utc_now_iso()),
    )



def write_triage_compensating_event(
    conn: sqlite3.Connection,
    *,
    action: str,
    item_id: str,
    actor: str,
    reason: str | None,
    client_ip: str | None = None,
) -> None:
    """Write a compensating audit event after failed mutation rollback."""

    payload = {"item_id": item_id, "phase": "compensating"}
    if client_ip:
        payload["client_ip"] = client_ip
    compensating_details = json.dumps(payload)
    account_name = resolve_account_name(conn, item_id)
    conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, account_name, f"triage_{action}_compensating", reason, compensating_details, actor, _utc_now_iso()),
    )