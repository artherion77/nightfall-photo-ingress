from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


def _triage_headers(api_token: str, key: str) -> dict[str, str]:
    headers = auth_headers(api_token)
    headers["X-Idempotency-Key"] = key
    return headers


@pytest.mark.anyio
async def test_accept_removes_item_from_staging_list(api_client, api_token) -> None:
    before = await api_client.get("/api/v1/staging?limit=20", headers=auth_headers(api_token))
    assert before.status_code == 200
    before_payload = before.json()
    assert before_payload["total"] >= 1

    mutate = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=_triage_headers(api_token, "ui-triage-accept-1"),
        json={"reason": "operator_accept"},
    )
    assert mutate.status_code == 200

    after = await api_client.get("/api/v1/staging?limit=20", headers=auth_headers(api_token))
    assert after.status_code == 200
    after_payload = after.json()
    assert all(item["sha256"] != "abc123def456" for item in after_payload["items"])


@pytest.mark.anyio
async def test_reject_removes_item_from_staging_list(api_client, api_token) -> None:
    mutate = await api_client.post(
        "/api/v1/triage/xyz789uvw012/reject",
        headers=_triage_headers(api_token, "ui-triage-reject-1"),
        json={"reason": "operator_reject"},
    )
    assert mutate.status_code == 200

    after = await api_client.get("/api/v1/staging?limit=20", headers=auth_headers(api_token))
    assert after.status_code == 200
    after_payload = after.json()
    assert all(item["sha256"] != "xyz789uvw012" for item in after_payload["items"])


@pytest.mark.anyio
async def test_defer_requeues_item_to_pending(api_client, api_token, registry_conn) -> None:
    registry_conn.execute("UPDATE files SET status = 'accepted' WHERE sha256 = ?", ("abc123def456",))
    registry_conn.commit()

    mutate = await api_client.post(
        "/api/v1/triage/abc123def456/defer",
        headers=_triage_headers(api_token, "ui-triage-defer-1"),
        json={"reason": "operator_defer"},
    )
    assert mutate.status_code == 200

    after = await api_client.get("/api/v1/staging?limit=20", headers=auth_headers(api_token))
    assert after.status_code == 200
    after_payload = after.json()
    assert any(item["sha256"] == "abc123def456" for item in after_payload["items"])


@pytest.mark.anyio
async def test_duplicate_idempotency_key_returns_same_result(api_client, api_token) -> None:
    key = "ui-triage-replay-1"
    first = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=_triage_headers(api_token, key),
        json={"reason": "operator_accept"},
    )
    second = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=_triage_headers(api_token, key),
        json={"reason": "operator_accept"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
