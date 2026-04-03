"""Staging list/detail endpoint tests for Chunk 1."""

from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_staging_returns_paginated_shape(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/staging?limit=1", headers=auth_headers(api_token))
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "cursor" in payload
    assert "has_more" in payload
    assert "total" in payload
    assert len(payload["items"]) == 1


@pytest.mark.anyio
async def test_staging_after_cursor_returns_next_page(api_client, api_token: str) -> None:
    first = await api_client.get("/api/v1/staging?limit=1", headers=auth_headers(api_token))
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["cursor"] is not None

    second = await api_client.get(
        f"/api/v1/staging?limit=1&after={first_payload['cursor']}",
        headers=auth_headers(api_token),
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert len(second_payload["items"]) == 1
    assert second_payload["items"][0]["sha256"] != first_payload["items"][0]["sha256"]


@pytest.mark.anyio
async def test_item_detail_returns_record(api_client, api_token: str) -> None:
    response = await api_client.get(
        "/api/v1/items/abc123def456",
        headers=auth_headers(api_token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sha256"] == "abc123def456"


@pytest.mark.anyio
async def test_item_detail_404_for_missing(api_client, api_token: str) -> None:
    response = await api_client.get(
        "/api/v1/items/does-not-exist",
        headers=auth_headers(api_token),
    )
    assert response.status_code == 404
