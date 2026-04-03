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
@pytest.mark.parametrize("path", [
    "/api/v1/health",
    "/api/v1/staging",
    "/api/v1/audit-log",
    "/api/v1/config/effective",
    "/api/v1/blocklist",
])
async def test_literal_undefined_token_rejected_on_all_endpoints(api_client, path) -> None:
    """Regression: the literal string 'undefined' must be rejected as an invalid token.

    This documents the failure mode produced by a mis-compiled SPA bundle when
    import.meta.env.PUBLIC_API_TOKEN is used instead of $env/static/public.
    The Vite bundler leaves the reference unresolved and the fetch call sends
    'Authorization: Bearer undefined' verbatim.  The API must NOT treat this as a
    valid token under any circumstances.

    See audit/open-points/chunk3-ui-drift-analysis.md §2 Bug A.
    """
    response = await api_client.get(
        path,
        headers={"Authorization": "Bearer undefined"},
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
