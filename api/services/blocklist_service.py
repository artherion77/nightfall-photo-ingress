"""Blocklist service for read path queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sqlite3

from api.schemas import BlockRule, BlockRuleCreate, BlockRuleDeleteResponse, BlockRuleList, BlockRuleUpdate


class BlocklistService:
    """Provides blocklist data."""

    def __init__(self, registry_conn: sqlite3.Connection):
        self.conn = registry_conn

    def get_blocklist(self) -> BlockRuleList:
        """Get all block rules."""

        rows = self.conn.execute(
            "SELECT id, pattern, rule_type, reason, enabled, created_at, updated_at "
            "FROM blocked_rules ORDER BY id"
        ).fetchall()

        rules = [
            BlockRule(
                id=row[0],
                pattern=row[1],
                rule_type=row[2],
                reason=row[3],
                enabled=bool(row[4]),
                created_at=row[5],
                updated_at=row[6],
            )
            for row in rows
        ]
        return BlockRuleList(rules=rules)

    def create_rule(self, *, payload: BlockRuleCreate, idempotency_key: str) -> tuple[int, BlockRule]:
        replayed = self._replay_if_present(
            idempotency_key=idempotency_key,
            action="blocklist_create",
            item_id=payload.pattern,
            model=BlockRule,
        )
        if replayed is not None:
            return replayed

        now = datetime.now(UTC).isoformat()
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                """
                INSERT INTO blocked_rules (pattern, rule_type, reason, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (payload.pattern, payload.rule_type, payload.reason, int(payload.enabled), now, now),
            )
            row = self.conn.execute(
                "SELECT id, pattern, rule_type, reason, enabled, created_at, updated_at FROM blocked_rules WHERE id = ?",
                (int(cursor.lastrowid),),
            ).fetchone()
            assert row is not None
            result = BlockRule(
                id=row[0],
                pattern=row[1],
                rule_type=row[2],
                reason=row[3],
                enabled=bool(row[4]),
                created_at=row[5],
                updated_at=row[6],
            )
            self._persist_idempotency(
                idempotency_key=idempotency_key,
                action="blocklist_create",
                item_id=payload.pattern,
                response_status=201,
                response_body=result.model_dump(),
            )
            self.conn.commit()
            return 201, result
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise ValueError("Blocklist pattern already exists or rule_type invalid") from exc
        except Exception:
            self.conn.rollback()
            raise

    def update_rule(self, *, rule_id: int, payload: BlockRuleUpdate, idempotency_key: str) -> tuple[int, BlockRule]:
        replayed = self._replay_if_present(
            idempotency_key=idempotency_key,
            action="blocklist_update",
            item_id=str(rule_id),
            model=BlockRule,
        )
        if replayed is not None:
            return replayed

        current = self.conn.execute(
            "SELECT id, pattern, rule_type, reason, enabled, created_at, updated_at FROM blocked_rules WHERE id = ?",
            (rule_id,),
        ).fetchone()
        if current is None:
            raise LookupError("Block rule not found")

        next_pattern = payload.pattern if payload.pattern is not None else current[1]
        next_rule_type = payload.rule_type if payload.rule_type is not None else current[2]
        next_reason = payload.reason if payload.reason is not None else current[3]
        next_enabled = int(payload.enabled) if payload.enabled is not None else int(current[4])
        now = datetime.now(UTC).isoformat()

        self.conn.execute("BEGIN")
        try:
            self.conn.execute(
                """
                UPDATE blocked_rules
                SET pattern = ?, rule_type = ?, reason = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_pattern, next_rule_type, next_reason, next_enabled, now, rule_id),
            )
            row = self.conn.execute(
                "SELECT id, pattern, rule_type, reason, enabled, created_at, updated_at FROM blocked_rules WHERE id = ?",
                (rule_id,),
            ).fetchone()
            assert row is not None
            result = BlockRule(
                id=row[0],
                pattern=row[1],
                rule_type=row[2],
                reason=row[3],
                enabled=bool(row[4]),
                created_at=row[5],
                updated_at=row[6],
            )
            self._persist_idempotency(
                idempotency_key=idempotency_key,
                action="blocklist_update",
                item_id=str(rule_id),
                response_status=200,
                response_body=result.model_dump(),
            )
            self.conn.commit()
            return 200, result
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise ValueError("Blocklist update violates uniqueness or rule_type constraints") from exc
        except Exception:
            self.conn.rollback()
            raise

    def delete_rule(self, *, rule_id: int, idempotency_key: str) -> tuple[int, BlockRuleDeleteResponse]:
        replayed = self._replay_if_present(
            idempotency_key=idempotency_key,
            action="blocklist_delete",
            item_id=str(rule_id),
            model=BlockRuleDeleteResponse,
        )
        if replayed is not None:
            return replayed

        row = self.conn.execute("SELECT id FROM blocked_rules WHERE id = ?", (rule_id,)).fetchone()
        if row is None:
            raise LookupError("Block rule not found")

        self.conn.execute("BEGIN")
        try:
            self.conn.execute("DELETE FROM blocked_rules WHERE id = ?", (rule_id,))
            result = BlockRuleDeleteResponse(id=rule_id, deleted=True)
            self._persist_idempotency(
                idempotency_key=idempotency_key,
                action="blocklist_delete",
                item_id=str(rule_id),
                response_status=200,
                response_body=result.model_dump(),
            )
            self.conn.commit()
            return 200, result
        except Exception:
            self.conn.rollback()
            raise

    def _replay_if_present(self, *, idempotency_key: str, action: str, item_id: str, model) -> tuple[int, object] | None:
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

        if row[0] != action or row[1] != item_id:
            raise ValueError("Idempotency key reuse conflict")

        body = json.loads(row[3])
        return int(row[2]), model(**body)

    def _persist_idempotency(
        self,
        *,
        idempotency_key: str,
        action: str,
        item_id: str,
        response_status: int,
        response_body: dict[str, object],
    ) -> None:
        now = datetime.now(UTC)
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
