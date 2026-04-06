"""CORS behavior tests for configured UI origin allowlist."""

from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_configured_origin_receives_cors_headers(api_client, api_token: str) -> None:
    response = await api_client.get(
        "/api/v1/health",
        headers={
            **auth_headers(api_token),
            "Origin": "http://localhost:8000",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"


@pytest.mark.anyio
async def test_unconfigured_origin_does_not_receive_allow_origin_header(api_client, api_token: str) -> None:
    response = await api_client.get(
        "/api/v1/health",
        headers={
            **auth_headers(api_token),
            "Origin": "https://evil.example",
        },
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.anyio
async def test_preflight_allows_configured_origin(api_client) -> None:
    response = await api_client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert "GET" in response.headers.get("access-control-allow-methods", "")
