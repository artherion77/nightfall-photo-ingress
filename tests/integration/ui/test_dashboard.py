from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_dashboard_data_endpoints_return_expected_shape(api_client, api_token, spa_build_stub) -> None:
    health = await api_client.get("/api/v1/health", headers=auth_headers(api_token))
    staging = await api_client.get("/api/v1/staging?limit=20", headers=auth_headers(api_token))
    audit = await api_client.get("/api/v1/audit-log?limit=5", headers=auth_headers(api_token))
    config = await api_client.get("/api/v1/config/effective", headers=auth_headers(api_token))

    assert health.status_code == 200
    assert staging.status_code == 200
    assert audit.status_code == 200
    assert config.status_code == 200

    health_json = health.json()
    assert "polling_ok" in health_json
    assert "registry_ok" in health_json

    staging_json = staging.json()
    assert "items" in staging_json
    assert "total" in staging_json

    audit_json = audit.json()
    assert "events" in audit_json

    config_json = config.json()
    assert "kpi_thresholds" in config_json


@pytest.mark.anyio
async def test_dashboard_root_serves_spa_shell(api_client, spa_build_stub) -> None:
    response = await api_client.get("/")
    assert response.status_code == 200
    assert "dashboard-shell" in response.text
