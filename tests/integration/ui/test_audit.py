from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_audit_first_page_and_filter(api_client, api_token) -> None:
    first_page = await api_client.get("/api/v1/audit-log?limit=1", headers=auth_headers(api_token))
    assert first_page.status_code == 200

    payload = first_page.json()
    assert len(payload["events"]) == 1
    assert payload["has_more"] is True
    assert payload["cursor"] is not None

    filtered = await api_client.get("/api/v1/audit-log?limit=10&action=accepted", headers=auth_headers(api_token))
    assert filtered.status_code == 200
    for event in filtered.json()["events"]:
        assert event["action"] == "accepted"


@pytest.mark.anyio
async def test_audit_load_more_cursor_returns_next_page(api_client, api_token) -> None:
    first = await api_client.get("/api/v1/audit-log?limit=1", headers=auth_headers(api_token))
    cursor = first.json()["cursor"]

    second = await api_client.get(f"/api/v1/audit-log?limit=1&after={cursor}", headers=auth_headers(api_token))
    assert second.status_code == 200
    assert len(second.json()["events"]) == 1
