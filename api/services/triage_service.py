"""Triage write-path service with idempotency support."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3

from api.audit_hook import resolve_account_name, write_triage_compensating_event, write_triage_requested_event
from api.schemas import TriageResponse
from api.services.thumbnail_service import ThumbnailService


class TriageService:
    """Executes triage state transitions for queue items."""

    _ACTION_TO_STATE = {
        "accept": "accepted",
        "reject": "rejected",
        "defer": "pending",
    }

    def __init__(
        self,
        registry_conn: sqlite3.Connection,
        thumbnail_cache_path: Path | None = None,
    ):
        self.conn = registry_conn
        self.thumbnail_cache_path = thumbnail_cache_path

    def execute(
        self,
        *,
        action: str,
        item_id: str,
        idempotency_key: str,
        reason: str | None,
        actor: str = "api",
        client_ip: str | None = None,
    ) -> tuple[int, TriageResponse]:
        """Apply one triage transition or replay prior response."""

        replayed = self._replay_if_present(
            idempotency_key=idempotency_key,
            action=action,
            item_id=item_id,
        )
        if replayed is not None:
            return replayed

        if action not in self._ACTION_TO_STATE:
            raise ValueError(f"Unsupported triage action: {action}")

        now = datetime.now(UTC)
        new_state = self._ACTION_TO_STATE[action]

        write_triage_requested_event(
            self.conn,
            action=action,
            item_id=item_id,
            actor=actor,
            reason=reason,
            client_ip=client_ip,
        )
        self.conn.commit()

        self.conn.execute("BEGIN")
        try:
            row = self.conn.execute(
                "SELECT status FROM files WHERE sha256 = ?",
                (item_id,),
            ).fetchone()
            if row is None:
                self.conn.rollback()
                raise LookupError("Item not found")

            self.conn.execute(
                "UPDATE files SET status = ?, updated_at = ? WHERE sha256 = ?",
                (new_state, now.isoformat(), item_id),
            )
            details_payload = {"item_id": item_id, "state": new_state, "phase": "applied"}
            if client_ip:
                details_payload["client_ip"] = client_ip
            details = json.dumps(details_payload)
            account_name = resolve_account_name(self.conn, item_id)
            self.conn.execute(
                """
                INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, account_name, f"triage_{action}_applied", reason, details, actor, now.isoformat()),
            )

            response = TriageResponse(
                action_correlation_id=idempotency_key,
                item_id=item_id,
                state=new_state,
            )
            self._persist_idempotency(
                idempotency_key=idempotency_key,
                action=action,
                item_id=item_id,
                response_status=200,
                response_body=response.model_dump(),
                now=now,
            )

            self.conn.commit()

            if action in {"accept", "reject"} and self.thumbnail_cache_path is not None:
                self._purge_thumbnail_best_effort(item_id)

            return 200, response
        except Exception:
            self.conn.rollback()
            write_triage_compensating_event(
                self.conn,
                action=action,
                item_id=item_id,
                actor=actor,
                reason=reason,
                client_ip=client_ip,
            )
            self.conn.commit()
            raise

    def _purge_thumbnail_best_effort(self, item_id: str) -> None:
        try:
            service = ThumbnailService(self.conn, self.thumbnail_cache_path)
            service.purge_cache_entry(item_id)
        except Exception:
            # Best-effort derivative-cache cleanup must never fail triage.
            return

    def _replay_if_present(
        self,
        *,
        idempotency_key: str,
        action: str,
        item_id: str,
    ) -> tuple[int, TriageResponse] | None:
        row = self.conn.execute(
            """
            SELECT action, item_id, response_status, response_body_json
            FROM ui_action_idempotency
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None

        if row["action"] != action or row["item_id"] != item_id:
            raise ValueError("Idempotency key reuse conflict")

        body = json.loads(row["response_body_json"])
        return int(row["response_status"]), TriageResponse(**body)

    def _persist_idempotency(
        self,
        *,
        idempotency_key: str,
        action: str,
        item_id: str,
        response_status: int,
        response_body: dict[str, object],
        now: datetime,
    ) -> None:
        expires = now + timedelta(days=1)
        self.conn.execute(
            """
            INSERT INTO ui_action_idempotency (
                idempotency_key,
                action,
                item_id,
                request_body_json,
                response_status,
                response_body_json,
                created_at,
                expires_at
            ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?)
            """,
            (
                idempotency_key,
                action,
                item_id,
                response_status,
                json.dumps(response_body),
                now.isoformat(),
                expires.isoformat(),
            ),
        )
