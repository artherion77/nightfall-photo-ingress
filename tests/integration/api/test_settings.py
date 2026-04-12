"""Integration tests for settings API endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.services.settings_service import SettingsService


@pytest.fixture
def client():
    """Create a test client with auth token."""
    app = create_app(
        config_path="/etc/nightfall/photo-ingress.conf",
    )
    client = TestClient(app)
    # Set up auth header
    client.headers = {"Authorization": "Bearer test-token"}
    return client


def test_get_kpi_thresholds_default(client):
    """GET /api/v1/settings/kpi-thresholds returns default thresholds."""
    # Reset to defaults first
    SettingsService.reset_kpi_thresholds()
    
    response = client.get("/api/v1/settings/kpi-thresholds")
    
    assert response.status_code == 200
    data = response.json()
    assert "thresholds" in data
    assert "updated_at" in data
    
    thresholds = data["thresholds"]
    assert thresholds["pending_warning"] == 100
    assert thresholds["pending_error"] == 500
    assert thresholds["disk_warning_percent"] == 80
    assert thresholds["disk_error_percent"] == 95


def test_get_kpi_thresholds_requires_auth(client):
    """GET without auth token returns 401."""
    app = create_app(config_path="/etc/nightfall/photo-ingress.conf")
    unauth_client = TestClient(app)
    
    response = unauth_client.get("/api/v1/settings/kpi-thresholds")
    assert response.status_code == 401


def test_put_kpi_thresholds_valid(client):
    """PUT /api/v1/settings/kpi-thresholds updates thresholds."""
    payload = {
        "pending_warning": 150,
        "pending_error": 600,
        "disk_warning_percent": 75,
        "disk_error_percent": 90,
    }
    
    response = client.put("/api/v1/settings/kpi-thresholds", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    thresholds = data["thresholds"]
    assert thresholds["pending_warning"] == 150
    assert thresholds["pending_error"] == 600
    assert thresholds["disk_warning_percent"] == 75
    assert thresholds["disk_error_percent"] == 90
    
    # Verify persistence across requests
    response2 = client.get("/api/v1/settings/kpi-thresholds")
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["thresholds"]["pending_warning"] == 150


def test_put_kpi_thresholds_validation_error_pending(client):
    """PUT with pending_error <= pending_warning returns 422."""
    payload = {
        "pending_warning": 500,
        "pending_error": 500,  # Must be > warning
        "disk_warning_percent": 80,
        "disk_error_percent": 95,
    }
    
    response = client.put("/api/v1/settings/kpi-thresholds", json=payload)
    
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data or "detail" in str(data)


def test_put_kpi_thresholds_validation_error_disk(client):
    """PUT with disk_error_percent <= disk_warning_percent returns 422."""
    payload = {
        "pending_warning": 100,
        "pending_error": 500,
        "disk_warning_percent": 90,
        "disk_error_percent": 85,  # Must be > warning
    }
    
    response = client.put("/api/v1/settings/kpi-thresholds", json=payload)
    
    assert response.status_code == 422


def test_patch_kpi_thresholds_partial(client):
    """PATCH /api/v1/settings/kpi-thresholds updates selected fields."""
    # Set initial state
    SettingsService.reset_kpi_thresholds()
    
    payload = {
        "pending_warning": 120,
        "pending_error": 550,
        "disk_warning_percent": 80,
        "disk_error_percent": 95,
    }
    
    response = client.patch("/api/v1/settings/kpi-thresholds", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    thresholds = data["thresholds"]
    assert thresholds["pending_warning"] == 120
    assert thresholds["pending_error"] == 550


def test_delete_kpi_thresholds_resets(client):
    """DELETE /api/v1/settings/kpi-thresholds resets to defaults."""
    # First, update to non-default values
    payload = {
        "pending_warning": 200,
        "pending_error": 700,
        "disk_warning_percent": 70,
        "disk_error_percent": 92,
    }
    client.put("/api/v1/settings/kpi-thresholds", json=payload)
    
    # Now reset
    response = client.delete("/api/v1/settings/kpi-thresholds")
    
    assert response.status_code == 200
    data = response.json()
    thresholds = data["thresholds"]
    assert thresholds["pending_warning"] == 100
    assert thresholds["pending_error"] == 500
    assert thresholds["disk_warning_percent"] == 80
    assert thresholds["disk_error_percent"] == 95


def test_put_kpi_thresholds_boundary_values(client):
    """PUT with boundary values succeeds."""
    payload = {
        "pending_warning": 1,
        "pending_error": 2,
        "disk_warning_percent": 1,
        "disk_error_percent": 2,
    }
    
    response = client.put("/api/v1/settings/kpi-thresholds", json=payload)
    
    assert response.status_code == 200


def test_put_kpi_thresholds_out_of_range(client):
    """PUT with out-of-range values returns 422."""
    payload = {
        "pending_warning": 0,  # Must be >= 1
        "pending_error": 500,
        "disk_warning_percent": 80,
        "disk_error_percent": 95,
    }
    
    response = client.put("/api/v1/settings/kpi-thresholds", json=payload)
    
    assert response.status_code == 422


def test_settings_response_has_updated_at(client):
    """All settings responses include updated_at timestamp."""
    response = client.get("/api/v1/settings/kpi-thresholds")
    
    assert response.status_code == 200
    data = response.json()
    assert "updated_at" in data
    assert data["updated_at"]  # Non-empty
    assert "T" in data["updated_at"]  # ISO-8601 format
    assert "Z" in data["updated_at"]  # UTC timezone
