"""Blocklist service for read path queries."""

from __future__ import annotations

import sqlite3

from api.schemas import BlockRule, BlockRuleList


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
