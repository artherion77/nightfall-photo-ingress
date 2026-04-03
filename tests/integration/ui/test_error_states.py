from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_error_state_unauthorized_for_missing_token(api_client) -> None:
    response = await api_client.get("/api/v1/staging")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_spa_fallback_for_client_route(api_client, spa_build_stub) -> None:
    response = await api_client.get("/audit")
    assert response.status_code == 200
    assert "spa-fallback" in response.text
