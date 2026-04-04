from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_staging_queue_returns_pending_items_for_display(api_client, api_token) -> None:
    response = await api_client.get("/api/v1/staging?limit=20", headers=auth_headers(api_token))
    assert response.status_code == 200

    payload = response.json()
    assert isinstance(payload["items"], list)
    assert payload["total"] >= len(payload["items"])
    assert payload["items"][0]["filename"]


@pytest.mark.anyio
async def test_staging_chunk_exposes_triage_endpoint_with_idempotency_requirement(api_client, api_token) -> None:
    response = await api_client.post(
        "/api/v1/triage/abc123def456/accept",
        headers=auth_headers(api_token),
        json={},
    )
    assert response.status_code == 422
