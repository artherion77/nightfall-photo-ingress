"""Unit tests for poller status detection in health service."""

from __future__ import annotations

import fcntl
from pathlib import Path

from api.services import health_service


def test_get_poller_status_reports_in_progress_when_poll_lock_is_held(
    monkeypatch,
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "registry.poll.lock"

    monkeypatch.setattr(health_service, "_systemctl_is_active", lambda _unit: "inactive")

    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        status = health_service.get_poller_status(lock_path=lock_path)

    assert status == "in_progress"


def test_get_poller_status_falls_back_to_timer_state_when_lock_is_free(
    monkeypatch,
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "registry.poll.lock"

    def fake_systemctl(unit: str) -> str:
        if unit == health_service._SERVICE_UNIT:
            return "inactive"
        if unit == health_service._TIMER_UNIT:
            return "inactive"
        return "unknown"

    monkeypatch.setattr(health_service, "_systemctl_is_active", fake_systemctl)

    status = health_service.get_poller_status(lock_path=lock_path)

    assert status == "timer_stopped"
