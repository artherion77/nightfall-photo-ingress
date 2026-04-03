"""Effective config endpoint tests for Chunk 1."""

from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_effective_config_redacts_api_token(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/config/effective", headers=auth_headers(api_token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_token"] == "[redacted]"


@pytest.mark.anyio
async def test_effective_config_contains_thresholds(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/config/effective", headers=auth_headers(api_token))
    assert response.status_code == 200
    payload = response.json()
    assert "kpi_thresholds" in payload
