"""Audit service for paginated event retrieval."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import PurePosixPath

from api.schemas import AuditDailySummary, AuditEvent, AuditPage


_ACTION_DESCRIPTIONS: dict[str, str] = {
    "pending": "File queued for triage",
    "accepted": "File accepted",
    "rejected": "File rejected",
    "discard_rejected": "Rejected file discarded",
    "triage_accept_requested": "Accept requested",
    "triage_accept_applied": "Accept applied",
    "triage_reject_requested": "Reject requested",
    "triage_reject_applied": "Reject applied",
    "triage_defer_requested": "Defer requested",
    "triage_defer_applied": "Defer applied",
    "auth_failure": "Authentication failed",
}


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
            "FROM audit_log"
        )
        params: list[object] = []

        conditions: list[str] = []
        if cursor_id:
            # Descending pagination: follow-up pages fetch rows older than the last id.
            conditions.append("id < ?")
            params.append(cursor_id)

        if action_filter:
            conditions.append("action = ?")
            params.append(action_filter)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit + 1)

        rows = self.conn.execute(query, params).fetchall()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        sha_values = [row[1] for row in rows if row[1]]
        filename_by_sha = self._filename_map_for_sha(sha_values)

        events: list[AuditEvent] = []
        for row in rows:
            details: dict = {}
            if row[5]:
                try:
                    details = json.loads(row[5])
                except json.JSONDecodeError:
                    details = {}

            action = row[3]
            description = self._describe_action(action)
            filename = self._derive_filename(details, row[1], filename_by_sha)

            events.append(
                AuditEvent(
                    id=row[0],
                    sha256=row[1],
                    account_name=row[2],
                    client_ip=(details.get("client_ip") if isinstance(details.get("client_ip"), str) else None),
                    action=action,
                    description=description,
                    reason=row[4],
                    filename=filename,
                    details=details,
                    actor=row[6],
                    ts=row[7],
                )
            )

        next_cursor = str(events[-1].id) if has_more and events else None
        return AuditPage(events=events, cursor=next_cursor, has_more=has_more)

    def get_daily_outcome_summary(self) -> AuditDailySummary:
        """Return accepted/rejected outcome counts for the current UTC day."""

        day_utc = datetime.now(UTC).date().isoformat()
        row = self.conn.execute(
            """
            SELECT
              SUM(CASE WHEN action IN ('accepted', 'triage_accept_applied') THEN 1 ELSE 0 END) AS accepted_today,
              SUM(CASE WHEN action IN ('rejected', 'triage_reject_applied') THEN 1 ELSE 0 END) AS rejected_today
            FROM audit_log
            WHERE DATE(ts) = DATE('now')
            """
        ).fetchone()

        accepted_today = int(row[0] or 0) if row else 0
        rejected_today = int(row[1] or 0) if row else 0
        return AuditDailySummary(
            day_utc=day_utc,
            accepted_today=accepted_today,
            rejected_today=rejected_today,
        )

    @staticmethod
    def _describe_action(action: str) -> str:
        if action in _ACTION_DESCRIPTIONS:
            return _ACTION_DESCRIPTIONS[action]
        return action.replace("_", " ").strip().capitalize()

    @staticmethod
    def _derive_filename(
        details: dict,
        sha256: str | None,
        filename_by_sha: dict[str, str],
    ) -> str | None:
        raw_name = details.get("filename") or details.get("original_filename")
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip()

        path_value = details.get("path") or details.get("path_hint")
        if isinstance(path_value, str) and path_value.strip():
            name = PurePosixPath(path_value).name.strip()
            if name:
                return name

        if sha256:
            return filename_by_sha.get(sha256)
        return None

    def _filename_map_for_sha(self, sha_values: list[str]) -> dict[str, str]:
        unique_sha = sorted({sha for sha in sha_values if isinstance(sha, str) and sha})
        if not unique_sha:
            return {}

        placeholders = ",".join("?" for _ in unique_sha)
        query = (
            "SELECT sha256, original_filename FROM files "
            f"WHERE sha256 IN ({placeholders}) AND original_filename IS NOT NULL"
        )
        rows = self.conn.execute(query, unique_sha).fetchall()
        return {
            row[0]: row[1]
            for row in rows
            if isinstance(row[0], str) and isinstance(row[1], str) and row[1].strip()
        }
