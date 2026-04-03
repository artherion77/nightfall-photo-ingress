"""Staging service for read-only queue queries."""

from __future__ import annotations

import sqlite3

from api.schemas import StagingItem, StagingPage


class StagingService:
    """Provides staging queue data."""

    def __init__(self, registry_conn: sqlite3.Connection):
        self.conn = registry_conn

    def get_staging_items(self, limit: int = 20, after_cursor: str | None = None) -> StagingPage:
        """Get paginated pending items from registry."""

        query = """
            SELECT f.sha256, f.original_filename, f.size_bytes,
                   f.first_seen_at, f.updated_at,
                   fo.account, fo.onedrive_id
            FROM files f
            LEFT JOIN file_origins fo ON f.sha256 = fo.sha256
            WHERE f.status = 'pending'
        """
        params: list[object] = []

        if after_cursor:
            query += " AND f.sha256 > ?"
            params.append(after_cursor)

        query += " ORDER BY f.sha256 LIMIT ?"
        params.append(limit + 1)

        rows = self.conn.execute(query, params).fetchall()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        items = [
            StagingItem(
                sha256=row[0],
                filename=row[1] or "unknown",
                size_bytes=row[2] or 0,
                first_seen_at=row[3],
                updated_at=row[4],
                account=row[5],
                onedrive_id=row[6],
            )
            for row in rows
        ]

        next_cursor = items[-1].sha256 if has_more and items else None
        total = int(self.conn.execute("SELECT COUNT(*) FROM files WHERE status = 'pending'").fetchone()[0])

        return StagingPage(items=items, cursor=next_cursor, has_more=has_more, total=total)

    def get_item(self, item_id: str) -> StagingItem | None:
        """Get single item detail."""

        row = self.conn.execute(
            """
            SELECT f.sha256, f.original_filename, f.size_bytes,
                   f.first_seen_at, f.updated_at,
                   fo.account, fo.onedrive_id
            FROM files f
            LEFT JOIN file_origins fo ON f.sha256 = fo.sha256
            WHERE f.sha256 = ?
            """,
            (item_id,),
        ).fetchone()

        if not row:
            return None

        return StagingItem(
            sha256=row[0],
            filename=row[1] or "unknown",
            size_bytes=row[2] or 0,
            first_seen_at=row[3],
            updated_at=row[4],
            account=row[5],
            onedrive_id=row[6],
        )
