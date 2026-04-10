"""Audit log endpoint tests for Chunk 1."""

from __future__ import annotations

from datetime import UTC, datetime
import json

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


@pytest.mark.anyio
async def test_audit_log_daily_summary_counts_today(
    api_client,
    api_token: str,
    registry_conn,
) -> None:
    today_ts = datetime.now(UTC).strftime("%Y-%m-%dT12:00:00Z")
    registry_conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "abc123def456",
            "personal",
            "triage_accept_applied",
            "operator accepted",
            json.dumps({"source": "ui"}),
            "api",
            today_ts,
        ),
    )
    registry_conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "xyz789uvw012",
            "personal",
            "triage_reject_applied",
            "operator rejected",
            json.dumps({"source": "ui"}),
            "api",
            today_ts,
        ),
    )
    registry_conn.commit()

    response = await api_client.get(
        "/api/v1/audit-log/daily-summary",
        headers=auth_headers(api_token),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted_today"] == 1
    assert payload["rejected_today"] == 1
