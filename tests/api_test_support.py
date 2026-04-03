"""Shared fixtures and helpers for Chunk 1 API tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from api.app import create_app
from nightfall_photo_ingress.config import AppConfig, CoreConfig, LoggingConfig, WebConfig
from nightfall_photo_ingress.domain.registry import Registry


@pytest.fixture
def api_token() -> str:
    return "test-token-12345"


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "registry.db"


@pytest.fixture
def registry_conn(registry_path: Path) -> Iterator[sqlite3.Connection]:
    registry = Registry(registry_path)
    registry.initialize()
    conn = sqlite3.connect(registry_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        INSERT INTO files (sha256, size_bytes, status, original_filename, current_path, first_seen_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "abc123def456",
            1024000,
            "pending",
            "test_photo.jpg",
            "/staging/test_photo.jpg",
            "2026-04-03T10:00:00Z",
            "2026-04-03T10:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO files (sha256, size_bytes, status, original_filename, current_path, first_seen_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "xyz789uvw012",
            2048000,
            "pending",
            "test_photo2.jpg",
            "/staging/test_photo2.jpg",
            "2026-04-03T11:00:00Z",
            "2026-04-03T11:00:00Z",
        ),
    )

    conn.execute(
        """
        INSERT INTO file_origins (account, onedrive_id, sha256, path_hint, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "personal",
            "abc!123",
            "abc123def456",
            "/photos/test_photo.jpg",
            "2026-04-03T10:00:00Z",
            "2026-04-03T10:00:00Z",
        ),
    )

    conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "abc123def456",
            "personal",
            "accepted",
            "operator accepted",
            json.dumps({"source": "ui"}),
            "api",
            "2026-04-03T10:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "xyz789uvw012",
            "personal",
            "rejected",
            "operator rejected",
            json.dumps({"source": "ui"}),
            "api",
            "2026-04-03T11:00:00Z",
        ),
    )

    conn.execute(
        """
        INSERT INTO blocked_rules (pattern, rule_type, reason, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "*.tmp",
            "filename",
            "Temporary files",
            1,
            "2026-04-03T09:00:00Z",
            "2026-04-03T09:00:00Z",
        ),
    )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def app_config(registry_path: Path, api_token: str) -> AppConfig:
    return AppConfig(
        source_path=Path("/tmp/test.conf"),
        core=CoreConfig(
            config_version=2,
            poll_interval_minutes=15,
            process_accounts_in_config_order=True,
            staging_path=Path("/tmp/staging"),
            pending_path=Path("/tmp/pending"),
            accepted_path=Path("/tmp/accepted"),
            accepted_storage_template="{yyyy}/{mm}/{original}",
            rejected_path=Path("/tmp/rejected"),
            trash_path=Path("/tmp/trash"),
            registry_path=registry_path,
            staging_on_same_pool=False,
            storage_template="{yyyy}/{mm}/{original}",
            verify_sha256_on_first_download=True,
            max_downloads_per_poll=200,
            max_poll_runtime_seconds=300,
            tmp_ttl_minutes=120,
            failed_ttl_hours=24,
            orphan_ttl_days=7,
            live_photo_capture_tolerance_seconds=3,
            live_photo_stem_mode="exact_stem",
            live_photo_component_order="photo_first",
            live_photo_conflict_policy="nearest_capture_time",
            sync_hash_import_enabled=True,
            sync_hash_import_path=Path("/tmp/sync"),
            sync_hash_import_glob=".hashes.sha1",
        ),
        logging=LoggingConfig(log_level="INFO", console_format="json"),
        web=WebConfig(api_token=api_token, bind_host="127.0.0.1", bind_port=8000),
        accounts=(),
    )


@pytest.fixture
async def api_client(
    app_config: AppConfig, registry_conn: sqlite3.Connection
) -> AsyncIterator[AsyncClient]:
    app = create_app(app_config=app_config, registry_conn=registry_conn)
    app.state.app_config = app_config
    app.state.registry_conn = registry_conn
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def auth_headers(api_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_token}"}
