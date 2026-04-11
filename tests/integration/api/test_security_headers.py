"""Security header policy tests for localhost deployment mode."""

from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_security_headers_present_on_authenticated_api_response(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/health", headers=auth_headers(api_token))

    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.anyio
async def test_security_headers_present_on_docs_response(api_client) -> None:
    response = await api_client.get("/api/docs")

    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.anyio
async def test_security_headers_present_on_preflight_response(api_client) -> None:
    response = await api_client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://staging-photo-ingress.home.arpa",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
