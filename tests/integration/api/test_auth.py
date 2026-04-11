"""Authentication and docs auth-exemption tests for Chunk 1."""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.integration.api.support import auth_headers


def _latest_auth_failure_row(registry_conn: sqlite3.Connection):
    return registry_conn.execute(
        """
        SELECT action, reason, details_json, actor
        FROM audit_log
        WHERE action = 'auth_failure'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


@pytest.mark.anyio
async def test_missing_bearer_returns_401(api_client, registry_conn: sqlite3.Connection) -> None:
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 401

    row = _latest_auth_failure_row(registry_conn)
    assert row is not None
    assert row["action"] == "auth_failure"
    assert row["actor"] == "api_auth"
    assert row["reason"] == "Missing Authorization header"
    details = json.loads(row["details_json"])
    assert details["path"] == "/api/v1/health"
    assert details["method"] == "GET"
    assert details["status_code"] == 401


@pytest.mark.anyio
async def test_invalid_bearer_returns_401(api_client, registry_conn: sqlite3.Connection) -> None:
    response = await api_client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401

    row = _latest_auth_failure_row(registry_conn)
    assert row is not None
    assert row["action"] == "auth_failure"
    assert row["actor"] == "api_auth"
    assert row["reason"] == "Invalid token"
    details = json.loads(row["details_json"])
    assert details["path"] == "/api/v1/health"
    assert details["method"] == "GET"
    assert details["status_code"] == 401


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
    assert "/api/v1/poll/trigger" in paths
    assert "/api/v1/staging" in paths
    assert "/api/v1/items/{item_id}" in paths
    assert "/api/v1/audit-log" in paths
    assert "/api/v1/audit/log" in paths
    assert "/api/v1/audit-log/daily-summary" in paths
    assert "/api/v1/audit/log/daily-summary" in paths
    assert "/api/v1/config/effective" in paths
    assert "/api/v1/blocklist" in paths
    assert "/api/v1/blocklist/{rule_id}" in paths
    assert "/api/v1/triage/{item_id}/accept" in paths
    assert "/api/v1/triage/{item_id}/reject" in paths
    assert "/api/v1/triage/{item_id}/defer" in paths
    assert "/api/v1/thumbnails/{sha256}" in paths

    # C5 guardrail: no v2 surface is introduced in current Phase 2 scope.
    assert not any(path.startswith("/api/v2") for path in paths)


@pytest.mark.anyio
async def test_valid_bearer_allows_access(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/health", headers=auth_headers(api_token))
    assert response.status_code == 200
