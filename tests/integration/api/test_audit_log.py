"""Audit log endpoint tests for Chunk 1."""

from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_audit_log_pagination(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/audit-log?limit=1", headers=auth_headers(api_token))
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["events"]) == 1
    assert "cursor" in payload


@pytest.mark.anyio
async def test_audit_log_action_filter(api_client, api_token: str) -> None:
    response = await api_client.get(
        "/api/v1/audit-log?action=accepted",
        headers=auth_headers(api_token),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["events"]
    assert all(event["action"] == "accepted" for event in payload["events"])


@pytest.mark.anyio
async def test_audit_log_rejects_invalid_limit(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/audit-log?limit=0", headers=auth_headers(api_token))
    assert response.status_code == 422
