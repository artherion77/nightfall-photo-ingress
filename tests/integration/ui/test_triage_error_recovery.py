from __future__ import annotations

import pytest

from api.services.triage_service import TriageService
from tests.integration.api.support import auth_headers


def _triage_headers(api_token: str, key: str) -> dict[str, str]:
    headers = auth_headers(api_token)
    headers["X-Idempotency-Key"] = key
    return headers


@pytest.mark.anyio
async def test_triage_failure_keeps_item_pending(api_client, api_token, registry_conn, monkeypatch) -> None:
    original_execute = TriageService.execute

    def failing_execute(self, *, action, item_id, idempotency_key, reason, actor="api"):
        if action == "accept":
            raise RuntimeError("simulated triage failure")
        return original_execute(
            self,
            action=action,
            item_id=item_id,
            idempotency_key=idempotency_key,
            reason=reason,
            actor=actor,
        )

    monkeypatch.setattr(TriageService, "execute", failing_execute)

    response = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=_triage_headers(api_token, "ui-triage-fail-1"),
        json={"reason": "operator_accept"},
    )
    assert response.status_code == 500

    row = registry_conn.execute(
        "SELECT status FROM files WHERE sha256 = ?",
        ("abc123def456",),
    ).fetchone()
    assert row is not None
    assert row["status"] == "pending"
