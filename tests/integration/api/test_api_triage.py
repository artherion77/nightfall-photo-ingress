"""Triage mutation API tests for Chunk 4."""

from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


def _idempotency_headers(api_token: str, key: str) -> dict[str, str]:
    headers = auth_headers(api_token)
    headers["X-Idempotency-Key"] = key
    return headers


@pytest.mark.anyio
async def test_accept_transitions_item_to_accepted(api_client, api_token: str, registry_conn) -> None:
    response = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=_idempotency_headers(api_token, "triage-accept-1"),
        json={"reason": "operator_accept"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["item_id"] == "abc123def456"
    assert payload["state"] == "accepted"

    row = registry_conn.execute(
        "SELECT status FROM files WHERE sha256 = ?",
        ("abc123def456",),
    ).fetchone()
    assert row is not None
    assert row["status"] == "accepted"


@pytest.mark.anyio
async def test_reject_transitions_item_to_rejected(api_client, api_token: str, registry_conn) -> None:
    response = await api_client.post(
        "/api/v1/triage/xyz789uvw012/reject",
        headers=_idempotency_headers(api_token, "triage-reject-1"),
        json={"reason": "operator_reject"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "rejected"

    row = registry_conn.execute(
        "SELECT status FROM files WHERE sha256 = ?",
        ("xyz789uvw012",),
    ).fetchone()
    assert row is not None
    assert row["status"] == "rejected"


@pytest.mark.anyio
async def test_defer_returns_item_to_pending(api_client, api_token: str, registry_conn) -> None:
    registry_conn.execute(
        "UPDATE files SET status = 'accepted' WHERE sha256 = ?",
        ("xyz789uvw012",),
    )
    registry_conn.commit()

    response = await api_client.post(
        "/api/v1/triage/xyz789uvw012/defer",
        headers=_idempotency_headers(api_token, "triage-defer-1"),
        json={"reason": "operator_defer"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "pending"

    row = registry_conn.execute(
        "SELECT status FROM files WHERE sha256 = ?",
        ("xyz789uvw012",),
    ).fetchone()
    assert row is not None
    assert row["status"] == "pending"


@pytest.mark.anyio
async def test_missing_idempotency_key_returns_422(api_client, api_token: str) -> None:
    response = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=auth_headers(api_token),
        json={"reason": "operator_accept"},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_invalid_item_id_returns_404(api_client, api_token: str) -> None:
    response = await api_client.post(
        "/api/v1/triage/not-found/accept",
        headers=_idempotency_headers(api_token, "triage-404"),
        json={"reason": "operator_accept"},
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_duplicate_idempotency_key_replays_same_response(api_client, api_token: str, registry_conn) -> None:
    key = "triage-replay-1"
    first = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=_idempotency_headers(api_token, key),
        json={"reason": "operator_accept"},
    )
    second = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=_idempotency_headers(api_token, key),
        json={"reason": "operator_accept"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    row = registry_conn.execute(
        "SELECT COUNT(*) AS n FROM ui_action_idempotency WHERE idempotency_key = ?",
        (key,),
    ).fetchone()
    assert row is not None
    assert int(row["n"]) == 1
