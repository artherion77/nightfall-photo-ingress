"""Health endpoint contract tests for Chunk 1."""

from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_health_schema_and_status(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/health", headers=auth_headers(api_token))
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) >= {
        "polling_ok",
        "auth_ok",
        "registry_ok",
        "disk_ok",
        "last_updated_at",
    }
