"""Tests for Chunk 1: Read-Only API endpoints."""

import pytest
import sqlite3
import json
from pathlib import Path

from nightfall_photo_ingress.config import AppConfig, CoreConfig, WebConfig, LoggingConfig
from nightfall_photo_ingress.domain.registry import Registry
from api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def test_registry_db(tmp_path: Path) -> sqlite3.Connection:
    """Create a test registry database with sample data."""
    
    registry_path = tmp_path / "test.db"
    registry = Registry(registry_path)
    registry.initialize()
    
    conn = sqlite3.connect(registry_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    # Add test pending items
    conn.execute(
        """INSERT INTO files (sha256, size_bytes, status, original_filename, current_path, first_seen_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("abc123def456", 1024000, "pending", "test_photo.jpg", "/staging/test_photo.jpg",
         "2026-04-03T10:00:00Z", "2026-04-03T10:00:00Z"),
    )
    conn.execute(
        """INSERT INTO files (sha256, size_bytes, status, original_filename, current_path, first_seen_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("xyz789uvw012", 2048000, "pending", "test_photo2.jpg", "/staging/test_photo2.jpg",
         "2026-04-03T11:00:00Z", "2026-04-03T11:00:00Z"),
    )
    
    # Add file origins
    conn.execute(
        """INSERT INTO file_origins (account, onedrive_id, sha256, path_hint, first_seen_at, last_seen_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("personal", "abc!123", "abc123def456", "/photos/test_photo.jpg",
         "2026-04-03T10:00:00Z", "2026-04-03T10:00:00Z"),
    )
    
    # Add audit log events
    conn.execute(
        """INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("abc123def456", "personal", "ingested", "New file from OneDrive",
         json.dumps({"source": "onedrive"}), "ingest", "2026-04-03T10:00:00Z"),
    )
    conn.execute(
        """INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("xyz789uvw012", "personal", "ingested", "New file from OneDrive",
         json.dumps({"source": "onedrive"}), "ingest", "2026-04-03T11:00:00Z"),
    )
    
    # Add blocklist rules
    conn.execute(
        """INSERT INTO blocked_rules (pattern, rule_type, reason, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("*.tmp", "filename", "Temporary files", 1, "2026-04-03T09:00:00Z", "2026-04-03T09:00:00Z"),
    )
    
    conn.commit()
    return conn


@pytest.fixture
def test_config(test_registry_db: sqlite3.Connection, tmp_path: Path) -> AppConfig:
    """Create a test configuration."""
    
    registry_path = tmp_path / "test.db"
    
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
        web=WebConfig(api_token="test-token-12345", bind_host="127.0.0.1", bind_port=8000),
        accounts=(),
    )


@pytest.fixture
def client(test_config: AppConfig, test_registry_db: sqlite3.Connection):
    """Create a test HTTP client."""
    
    app = create_app()
    
    # Inject test config and connection into app globals
    import api.app
    api.app._app_config = test_config
    api.app._registry_conn = test_registry_db
    
    # Inject app config into auth
    from api.auth import set_app_config_for_auth
    set_app_config_for_auth(test_config)
    
    return TestClient(app)


# ===== TESTS =====

def test_health_requires_auth(client: TestClient):
    """Health endpoint requires authentication."""
    response = client.get("/api/v1/health")
    assert response.status_code == 401


def test_health_with_valid_token(client: TestClient):
    """Health endpoint with valid token returns 200."""
    response = client.get("/api/v1/health", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 200
    data = response.json()
    assert "polling_ok" in data
    assert "auth_ok" in data
    assert "registry_ok" in data
    assert "disk_ok" in data


def test_health_with_invalid_token(client: TestClient):
    """Health endpoint with invalid token returns 401."""
    response = client.get("/api/v1/health", headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401


def test_staging_returns_pending_items(client: TestClient):
    """Staging endpoint returns pending items."""
    response = client.get("/api/v1/staging", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "cursor" in data
    assert "has_more" in data
    assert "total" in data
    assert data["total"] == 2


def test_staging_pagination(client: TestClient):
    """Staging endpoint respects limit parameter."""
    response = client.get("/api/v1/staging?limit=1", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 1


def test_item_detail(client: TestClient):
    """Item detail endpoint returns single item."""
    response = client.get("/api/v1/items/abc123def456", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 200
    data = response.json()
    assert data["sha256"] == "abc123def456"
    assert data["filename"] == "test_photo.jpg"


def test_item_detail_not_found(client: TestClient):
    """Item detail returns 404 for nonexistent item."""
    response = client.get("/api/v1/items/nonexistent", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 404


def test_audit_log(client: TestClient):
    """Audit log endpoint returns events."""
    response = client.get("/api/v1/audit-log", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert len(data["events"]) >= 2


def test_audit_log_action_filter(client: TestClient):
    """Audit log filters by action parameter."""
    response = client.get("/api/v1/audit-log?action=ingested", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 200
    data = response.json()
    assert all(e["action"] == "ingested" for e in data["events"])


def test_config_redacts_token(client: TestClient):
    """Config endpoint redacts API token."""
    response = client.get("/api/v1/config/effective", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 200
    data = response.json()
    assert data["api_token"] == "[redacted]"


def test_config_includes_thresholds(client: TestClient):
    """Config endpoint includes KPI thresholds."""
    response = client.get("/api/v1/config/effective", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 200
    data = response.json()
    assert "kpi_thresholds" in data


def test_blocklist(client: TestClient):
    """Blocklist endpoint returns rules."""
    response = client.get("/api/v1/blocklist", headers={"Authorization": "Bearer test-token-12345"})
    assert response.status_code == 200
    data = response.json()
    assert "rules" in data
    assert len(data["rules"]) >= 1
    assert data["rules"][0]["pattern"] == "*.tmp"


def test_rapiddoc_no_auth(client: TestClient):
    """RapiDoc does not require auth."""
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert "rapi-doc" in response.text


def test_openapi_no_auth(client: TestClient):
    """OpenAPI does not require auth."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
