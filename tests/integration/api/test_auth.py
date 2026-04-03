"""Authentication and docs auth-exemption tests for Chunk 1."""

from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_missing_bearer_returns_401(api_client) -> None:
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_invalid_bearer_returns_401(api_client) -> None:
    response = await api_client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_docs_endpoint_does_not_require_auth(api_client) -> None:
    response = await api_client.get("/api/docs")
    assert response.status_code == 200
    assert "rapi-doc" in response.text


@pytest.mark.anyio
async def test_openapi_endpoint_does_not_require_auth(api_client) -> None:
    response = await api_client.get("/api/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/staging" in paths
    assert "/api/v1/audit-log" in paths
    assert "/api/v1/config/effective" in paths
    assert "/api/v1/blocklist" in paths


@pytest.mark.anyio
async def test_valid_bearer_allows_access(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/health", headers=auth_headers(api_token))
    assert response.status_code == 200
