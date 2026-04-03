"""Blocklist read-path endpoint tests for Chunk 1."""

from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_blocklist_lists_rules(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/blocklist", headers=auth_headers(api_token))
    assert response.status_code == 200
    payload = response.json()
    assert "rules" in payload
    assert payload["rules"]
    assert payload["rules"][0]["pattern"] == "*.tmp"
