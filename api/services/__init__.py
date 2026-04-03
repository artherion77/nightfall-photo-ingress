"""Services for reading data from domain/registry modules."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from nightfall_photo_ingress.config import AppConfig
from nightfall_photo_ingress.status import STATUS_FILE_PATH
from api.schemas import (
    HealthResponse,
    ServiceStatus,
    StagingPage,
    StagingItem,
    AuditPage,
    AuditEvent,
    EffectiveConfig,
    BlockRuleList,
    BlockRule,
)


class HealthService:
    """Provides health status information."""

    @staticmethod
    def get_health() -> HealthResponse:
        """Read health snapshot from status file."""

        try:
            if STATUS_FILE_PATH.exists():
                content = STATUS_FILE_PATH.read_text(encoding="utf-8")
                status_data = json.loads(content)
                success = status_data.get("success", False)
                updated_at = status_data.get("updated_at", "unknown")
            else:
                success = False
                updated_at = "never"

            # For Phase 1, return a basic health response
            return HealthResponse(
                polling_ok=ServiceStatus(
                    ok=success,
                    message="Ingest process is running" if success else "No status file found",
                ),
                auth_ok=ServiceStatus(ok=True, message="Auth OK"),
                registry_ok=ServiceStatus(ok=True, message="Registry OK"),
                disk_ok=ServiceStatus(ok=True, message="Disk OK"),
                last_updated_at=updated_at,
                error=None,
            )
        except Exception as e:
            return HealthResponse(
                polling_ok=ServiceStatus(ok=False, message=f"Error: {e}"),
                auth_ok=ServiceStatus(ok=False, message=f"Error: {e}"),
                registry_ok=ServiceStatus(ok=False, message=f"Error: {e}"),
                disk_ok=ServiceStatus(ok=False, message=f"Error: {e}"),
                last_updated_at="error",
                error=str(e),
            )


class StagingService:
    """Provides staging queue data."""

    def __init__(self, registry_conn: sqlite3.Connection):
        self.conn = registry_conn

    def get_staging_items(
        self, limit: int = 20, after_cursor: str | None = None
    ) -> StagingPage:
        """Get paginated pending items from registry."""

        # Query pending items (files with status='pending')
        # Use sha256 for cursor-based pagination
        query = """
            SELECT f.sha256, f.original_filename, f.size_bytes, 
                   f.first_seen_at, f.updated_at,
                   fo.account, fo.onedrive_id
            FROM files f
            LEFT JOIN file_origins fo ON f.sha256 = fo.sha256
            WHERE f.status = 'pending'
        """
        params = []
        
        if after_cursor:
            query += " AND f.sha256 > ?"
            params.append(after_cursor)
        
        query += " ORDER BY f.sha256 LIMIT ?"
        params.append(limit + 1)

        db_cursor = self.conn.execute(query, params)
        rows = db_cursor.fetchall()

        items = []
        has_more = False
        next_cursor = None

        if len(rows) > limit:
            has_more = True
            rows = rows[:limit]

        for row in rows:
            items.append(
                StagingItem(
                    sha256=row[0],
                    filename=row[1] or "unknown",
                    size_bytes=row[2] or 0,
                    first_seen_at=row[3],
                    updated_at=row[4],
                    account=row[5],
                    onedrive_id=row[6],
                )
            )

        next_cursor = None
        if has_more and items:
            next_cursor = items[-1].sha256

        # Get total count
        count_query = "SELECT COUNT(*) FROM files WHERE status = 'pending'"
        total = self.conn.execute(count_query).fetchone()[0]

        return StagingPage(
            items=items,
            cursor=next_cursor,
            has_more=has_more,
            total=total,
        )

    def get_item(self, item_id: str) -> StagingItem | None:
        """Get single item detail."""

        query = """
            SELECT f.sha256, f.original_filename, f.size_bytes,
                   f.first_seen_at, f.updated_at,
                   fo.account, fo.onedrive_id
            FROM files f
            LEFT JOIN file_origins fo ON f.sha256 = fo.sha256
            WHERE f.sha256 = ?
        """

        db_cursor = self.conn.execute(query, (item_id,))
        row = db_cursor.fetchone()

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
                pass

        query = "SELECT id, sha256, account_name, action, reason, details_json, actor, ts FROM audit_log WHERE id > ?"
        params = [cursor_id]

        if action_filter:
            query += " AND action = ?"
            params.append(action_filter)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit + 1)

        db_cursor = self.conn.execute(query, params)
        rows = db_cursor.fetchall()

        events = []
        has_more = False

        if len(rows) > limit:
            has_more = True
            rows = rows[:limit]

        for row in rows:
            details = {}
            if row[5]:
                try:
                    details = json.loads(row[5])
                except json.JSONDecodeError:
                    pass

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

        next_cursor = None
        if has_more and events:
            next_cursor = str(events[-1].id)

        return AuditPage(
            events=events,
            cursor=next_cursor,
            has_more=has_more,
        )


class ConfigService:
    """Provides configuration data."""

    @staticmethod
    def get_effective_config(app_config: AppConfig) -> EffectiveConfig:
        """Return effective config with secrets redacted."""

        return EffectiveConfig(
            config_version=app_config.core.config_version,
            poll_interval_minutes=app_config.core.poll_interval_minutes,
            registry_path=str(app_config.core.registry_path),
            staging_path=str(app_config.core.staging_path),
            pending_path=str(app_config.core.pending_path),
            accepted_path=str(app_config.core.accepted_path),
            rejected_path=str(app_config.core.rejected_path),
            trash_path=str(app_config.core.trash_path),
            storage_template=app_config.core.storage_template,
            accepted_storage_template=app_config.core.accepted_storage_template,
            verify_sha256_on_first_download=app_config.core.verify_sha256_on_first_download,
            max_downloads_per_poll=app_config.core.max_downloads_per_poll,
            max_poll_runtime_seconds=app_config.core.max_poll_runtime_seconds,
            kpi_thresholds={
                "pending_warning": 100,
                "pending_error": 500,
                "disk_warning_percent": 80,
                "disk_error_percent": 95,
            },
        )


class BlocklistService:
    """Provides blocklist data."""

    def __init__(self, registry_conn: sqlite3.Connection):
        self.conn = registry_conn

    def get_blocklist(self) -> BlockRuleList:
        """Get all block rules."""

        query = "SELECT id, pattern, rule_type, reason, enabled, created_at, updated_at FROM blocked_rules ORDER BY id"
        db_cursor = self.conn.execute(query)
        rows = db_cursor.fetchall()

        rules = []
        for row in rows:
            rules.append(
                BlockRule(
                    id=row[0],
                    pattern=row[1],
                    rule_type=row[2],
                    reason=row[3],
                    enabled=bool(row[4]),
                    created_at=row[5],
                    updated_at=row[6],
                )
            )

        return BlockRuleList(rules=rules)
