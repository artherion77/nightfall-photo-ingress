"""Health endpoint contract tests for Chunk 1."""

from __future__ import annotations

import fcntl
import json

import pytest

from tests.integration.api.support import auth_headers


@pytest.mark.anyio
async def test_health_schema_and_status(api_client, api_token: str) -> None:
    response = await api_client.get("/api/v1/health", headers=auth_headers(api_token))
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) >= {
        "polling_ok",
        "auth_ok",
        "registry_ok",
        "disk_ok",
        "last_updated_at",
    }


@pytest.mark.anyio
async def test_health_reports_in_progress_when_poll_lock_is_held(
    api_client,
    api_token: str,
    app_config,
) -> None:
    lock_path = app_config.core.registry_path.with_suffix(".poll.lock")

    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        response = await api_client.get("/api/v1/health", headers=auth_headers(api_token))

    assert response.status_code == 200
    assert response.json()["poller_status"] == "in_progress"


@pytest.mark.anyio
async def test_health_returns_poll_duration_s_from_status_file(
    api_client,
    api_token: str,
    tmp_path,
    monkeypatch,
) -> None:
    import api.services.health_service as health_svc

    status_file = tmp_path / "photo-ingress.json"
    status_payload = {
        "schema_version": 1,
        "service": "photo-ingress",
        "version": "2.0.0",
        "host": "test-host",
        "state": "healthy",
        "success": True,
        "command": "poll",
        "updated_at": "2026-04-10T12:00:00+00:00",
        "details": {"poll_duration_s": 7.42},
    }
    status_file.write_text(json.dumps(status_payload), encoding="utf-8")
    monkeypatch.setattr(health_svc, "STATUS_FILE_PATH", status_file)

    response = await api_client.get("/api/v1/health", headers=auth_headers(api_token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["poll_duration_s"] == pytest.approx(7.42)
