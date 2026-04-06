"""Triage mutation API tests for Chunk 4."""

from __future__ import annotations

import pytest

from api.services.triage_service import TriageService
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

    events = registry_conn.execute(
        """
        SELECT action, actor, sha256, ts
        FROM audit_log
        WHERE sha256 = ? AND action IN (?, ?)
        ORDER BY id ASC
        """,
        (
            "abc123def456",
            "triage_accept_requested",
            "triage_accept_applied",
        ),
    ).fetchall()
    assert [event["action"] for event in events] == [
        "triage_accept_requested",
        "triage_accept_applied",
    ]
    assert all(event["actor"] == "api" for event in events)
    assert all(event["sha256"] == "abc123def456" for event in events)
    assert all(event["ts"] for event in events)


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


@pytest.mark.anyio
async def test_failure_persists_requested_and_compensating_audit_events(
    api_client,
    api_token: str,
    registry_conn,
    monkeypatch,
) -> None:
    original_persist = TriageService._persist_idempotency

    def failing_persist(self, *, idempotency_key, action, item_id, response_status, response_body, now):
        raise RuntimeError("simulated idempotency persistence failure")

    monkeypatch.setattr(TriageService, "_persist_idempotency", failing_persist)

    response = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=_idempotency_headers(api_token, "triage-fail-audit-1"),
        json={"reason": "operator_accept"},
    )
    assert response.status_code == 500

    row = registry_conn.execute(
        "SELECT status FROM files WHERE sha256 = ?",
        ("abc123def456",),
    ).fetchone()
    assert row is not None
    assert row["status"] == "pending"

    events = registry_conn.execute(
        """
        SELECT action, actor, sha256, ts
        FROM audit_log
        WHERE sha256 = ? AND action IN (?, ?, ?)
        ORDER BY id ASC
        """,
        (
            "abc123def456",
            "triage_accept_requested",
            "triage_accept_applied",
            "triage_accept_compensating",
        ),
    ).fetchall()
    assert [event["action"] for event in events] == [
        "triage_accept_requested",
        "triage_accept_compensating",
    ]
    assert all(event["actor"] == "api" for event in events)
    assert all(event["sha256"] == "abc123def456" for event in events)
    assert all(event["ts"] for event in events)

    idempotency_row = registry_conn.execute(
        "SELECT COUNT(*) AS n FROM ui_action_idempotency WHERE idempotency_key = ?",
        ("triage-fail-audit-1",),
    ).fetchone()
    assert idempotency_row is not None
    assert int(idempotency_row["n"]) == 0

    monkeypatch.setattr(TriageService, "_persist_idempotency", original_persist)
