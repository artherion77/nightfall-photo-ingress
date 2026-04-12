"""Integration tests for settings API endpoints."""

from __future__ import annotations

import pytest

from api.services.settings_service import SettingsService
from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_get_kpi_thresholds_default(api_client, api_token: str) -> None:
    SettingsService.reset_kpi_thresholds()

    response = await api_client.get(
        "/api/v1/settings/kpi-thresholds",
        headers=auth_headers(api_token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["thresholds"] == {
        "pending_warning": 100,
        "pending_error": 500,
        "disk_warning_percent": 80,
        "disk_error_percent": 95,
    }
    assert data["updated_at"]


@pytest.mark.anyio
async def test_get_kpi_thresholds_requires_auth(api_client) -> None:
    response = await api_client.get("/api/v1/settings/kpi-thresholds")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_put_kpi_thresholds_valid(api_client, api_token: str) -> None:
    payload = {
        "pending_warning": 150,
        "pending_error": 600,
        "disk_warning_percent": 75,
        "disk_error_percent": 90,
    }
    response = await api_client.put(
        "/api/v1/settings/kpi-thresholds",
        headers=auth_headers(api_token),
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["thresholds"] == payload


@pytest.mark.anyio
async def test_put_kpi_thresholds_validation_error(api_client, api_token: str) -> None:
    payload = {
        "pending_warning": 500,
        "pending_error": 500,
        "disk_warning_percent": 80,
        "disk_error_percent": 95,
    }
    response = await api_client.put(
        "/api/v1/settings/kpi-thresholds",
        headers=auth_headers(api_token),
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_delete_kpi_thresholds_resets(api_client, api_token: str) -> None:
    response = await api_client.delete(
        "/api/v1/settings/kpi-thresholds",
        headers=auth_headers(api_token),
    )

    assert response.status_code == 200
    assert response.json()["thresholds"] == {
        "pending_warning": 100,
        "pending_error": 500,
        "disk_warning_percent": 80,
        "disk_error_percent": 95,
    }
