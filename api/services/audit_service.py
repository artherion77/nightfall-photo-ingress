"""Audit service for paginated event retrieval."""

from __future__ import annotations

import json
import sqlite3

from api.schemas import AuditEvent, AuditPage


class AuditService:
    """Provides audit log data."""

    def __init__(self, registry_conn: sqlite3.Connection):
        self.conn = registry_conn

    def get_audit_log(
        self,
        limit: int = 50,
        after_cursor: str | None = None,
        action_filter: str | None = None,
    ) -> AuditPage:
        """Get paginated audit events."""

        cursor_id = 0
        if after_cursor:
            try:
                cursor_id = int(after_cursor)
            except ValueError:
                cursor_id = 0

        query = (
            "SELECT id, sha256, account_name, action, reason, details_json, actor, ts "
            "FROM audit_log WHERE id > ?"
        )
        params: list[object] = [cursor_id]

        if action_filter:
            query += " AND action = ?"
            params.append(action_filter)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit + 1)

        rows = self.conn.execute(query, params).fetchall()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        events: list[AuditEvent] = []
        for row in rows:
            details: dict = {}
            if row[5]:
                try:
                    details = json.loads(row[5])
                except json.JSONDecodeError:
                    details = {}

            events.append(
                AuditEvent(
                    id=row[0],
                    sha256=row[1],
                    account_name=row[2],
                    action=row[3],
                    reason=row[4],
                    details=details,
                    actor=row[6],
                    ts=row[7],
                )
            )

        next_cursor = str(events[-1].id) if has_more and events else None
        return AuditPage(events=events, cursor=next_cursor, has_more=has_more)
