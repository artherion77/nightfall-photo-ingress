from __future__ import annotations

import pytest

from tests.integration.api.support import auth_headers


def _idem_headers(api_token: str, key: str) -> dict[str, str]:
    headers = auth_headers(api_token)
    headers["X-Idempotency-Key"] = key
    return headers


@pytest.mark.anyio
async def test_add_rule_appears_in_list(api_client, api_token: str) -> None:
    created = await api_client.post(
        "/api/v1/blocklist",
        headers=_idem_headers(api_token, "ui-block-add-1"),
        json={"pattern": "ui-add-*.jpg", "rule_type": "filename", "reason": "ui add", "enabled": True},
    )
    assert created.status_code == 201

    listed = await api_client.get("/api/v1/blocklist", headers=auth_headers(api_token))
    assert listed.status_code == 200
    assert any(rule["pattern"] == "ui-add-*.jpg" for rule in listed.json()["rules"])


@pytest.mark.anyio
async def test_toggle_enabled_updates_badge_state(api_client, api_token: str) -> None:
    created = await api_client.post(
        "/api/v1/blocklist",
        headers=_idem_headers(api_token, "ui-block-toggle-create"),
        json={"pattern": "ui-toggle-*.jpg", "rule_type": "filename", "reason": "ui toggle", "enabled": True},
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    toggled = await api_client.patch(
        f"/api/v1/blocklist/{rule_id}",
        headers=_idem_headers(api_token, "ui-block-toggle-update"),
        json={"enabled": False},
    )
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is False


@pytest.mark.anyio
async def test_delete_with_confirm_removes_rule(api_client, api_token: str) -> None:
    created = await api_client.post(
        "/api/v1/blocklist",
        headers=_idem_headers(api_token, "ui-block-delete-create"),
        json={"pattern": "ui-delete-*.jpg", "rule_type": "filename", "reason": "ui delete", "enabled": True},
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    deleted = await api_client.delete(
        f"/api/v1/blocklist/{rule_id}",
        headers=_idem_headers(api_token, "ui-block-delete-confirm"),
    )
    assert deleted.status_code == 200

    listed = await api_client.get("/api/v1/blocklist", headers=auth_headers(api_token))
    assert listed.status_code == 200
    assert all(rule["id"] != rule_id for rule in listed.json()["rules"])


@pytest.mark.anyio
async def test_cancel_delete_keeps_rule(api_client, api_token: str) -> None:
    created = await api_client.post(
        "/api/v1/blocklist",
        headers=_idem_headers(api_token, "ui-block-cancel-create"),
        json={"pattern": "ui-cancel-*.jpg", "rule_type": "filename", "reason": "ui cancel", "enabled": True},
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    # Simulate cancel by intentionally not calling DELETE endpoint.
    listed = await api_client.get("/api/v1/blocklist", headers=auth_headers(api_token))
    assert listed.status_code == 200
    assert any(rule["id"] == rule_id for rule in listed.json()["rules"])
