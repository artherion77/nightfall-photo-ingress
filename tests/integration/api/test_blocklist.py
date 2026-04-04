"""Blocklist read/write endpoint tests for Chunk 5."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightfall_photo_ingress.domain.ingest import IngestDecisionEngine, StagedCandidate
from nightfall_photo_ingress.domain.registry import Registry
from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_blocklist_lists_rules(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/blocklist", headers=auth_headers(api_token))
    assert response.status_code == 200
    payload = response.json()
    assert "rules" in payload
    assert payload["rules"]
    assert payload["rules"][0]["pattern"] == "*.tmp"


def _idem_headers(api_token: str, key: str) -> dict[str, str]:
    headers = auth_headers(api_token)
    headers["X-Idempotency-Key"] = key
    return headers


@pytest.mark.anyio
async def test_create_rule_persists_and_replays_with_idempotency(api_client, api_token: str) -> None:
    payload = {
        "pattern": "blocked-*.jpg",
        "rule_type": "filename",
        "reason": "Chunk5 create",
        "enabled": True,
    }
    first = await api_client.post(
        "/api/v1/blocklist",
        headers=_idem_headers(api_token, "block-create-1"),
        json=payload,
    )
    second = await api_client.post(
        "/api/v1/blocklist",
        headers=_idem_headers(api_token, "block-create-1"),
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()


@pytest.mark.anyio
async def test_update_rule_toggles_enabled(api_client, api_token: str) -> None:
    created = await api_client.post(
        "/api/v1/blocklist",
        headers=_idem_headers(api_token, "block-create-toggle"),
        json={"pattern": "toggle-*.jpg", "rule_type": "filename", "reason": "toggle", "enabled": True},
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    updated = await api_client.patch(
        f"/api/v1/blocklist/{rule_id}",
        headers=_idem_headers(api_token, "block-update-1"),
        json={"enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False


@pytest.mark.anyio
async def test_delete_rule_hard_deletes(api_client, api_token: str) -> None:
    created = await api_client.post(
        "/api/v1/blocklist",
        headers=_idem_headers(api_token, "block-create-delete"),
        json={"pattern": "delete-*.jpg", "rule_type": "filename", "reason": "delete", "enabled": True},
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    deleted = await api_client.delete(
        f"/api/v1/blocklist/{rule_id}",
        headers=_idem_headers(api_token, "block-delete-1"),
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"id": rule_id, "deleted": True}

    listed = await api_client.get("/api/v1/blocklist", headers=auth_headers(api_token))
    assert listed.status_code == 200
    assert all(rule["id"] != rule_id for rule in listed.json()["rules"])


@pytest.mark.anyio
async def test_ingest_honors_new_blocklist_rule(api_client, api_token: str, registry_path: Path) -> None:
    create = await api_client.post(
        "/api/v1/blocklist",
        headers=_idem_headers(api_token, "block-create-ingest"),
        json={"pattern": "blocked-*.jpg", "rule_type": "filename", "reason": "ingest", "enabled": True},
    )
    assert create.status_code == 201

    staging_root = registry_path.parent / "staging"
    pending_root = registry_path.parent / "pending"
    staging_root.mkdir(parents=True, exist_ok=True)
    pending_root.mkdir(parents=True, exist_ok=True)

    staged_file = staging_root / "blocked-photo.jpg"
    staged_file.write_bytes(b"blocked-content")

    registry = Registry(registry_path)
    registry.initialize()
    engine = IngestDecisionEngine(registry)

    result = engine.process_batch(
        candidates=[
            StagedCandidate(
                account_name="personal",
                onedrive_id="blocked-item-1",
                original_filename="blocked-photo.jpg",
                relative_path="/photos/blocked-photo.jpg",
                modified_time="2026-04-04T00:00:00Z",
                size_bytes=staged_file.stat().st_size,
                staging_path=staged_file,
            )
        ],
        pending_root=pending_root,
        storage_template="{yyyy}/{mm}/{original}",
        staging_on_same_pool=True,
    )

    assert result.outcomes[0].action == "discard_rejected"
    record = registry.get_file(sha256=result.outcomes[0].sha256 or "")
    assert record is not None
    assert record.status == "rejected"
