from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_settings_config_redacts_token(api_client, api_token) -> None:
    response = await api_client.get("/api/v1/config/effective", headers=auth_headers(api_token))
    assert response.status_code == 200

    payload = response.json()
    assert payload["api_token"] == "[redacted]"
    assert "kpi_thresholds" in payload
