"""Unit tests for rolling poll duration history store."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from api.services.poll_history import get_poll_history_7days, _record_current_poll


def _make_status_file(tmp_path: Path, *, updated_at: str, duration_s: float) -> Path:
    path = tmp_path / "photo-ingress.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "service": "photo-ingress",
                "state": "healthy",
                "success": True,
                "command": "poll",
                "updated_at": updated_at,
                "details": {"poll_duration_s": duration_s},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_get_poll_history_7days_returns_7_entries(tmp_path: Path) -> None:
    history_path = tmp_path / "history.jsonl"
    result = get_poll_history_7days(
        status_path=tmp_path / "nonexistent.json",
        history_path=history_path,
    )
    assert len(result) == 7


def test_get_poll_history_7days_fills_missing_with_zero(tmp_path: Path) -> None:
    history_path = tmp_path / "history.jsonl"
    result = get_poll_history_7days(
        status_path=tmp_path / "nonexistent.json",
        history_path=history_path,
    )
    assert all(e["duration_s"] == 0.0 for e in result)


def test_get_poll_history_7days_records_from_status_file(tmp_path: Path) -> None:
    today = datetime.now(UTC)
    ts = today.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    status_path = _make_status_file(tmp_path, updated_at=ts, duration_s=12.5)
    history_path = tmp_path / "history.jsonl"

    result = get_poll_history_7days(status_path=status_path, history_path=history_path)

    assert len(result) == 7
    today_entry = result[-1]  # last entry is today
    assert today_entry["duration_s"] == pytest.approx(12.5)


def test_record_current_poll_is_idempotent(tmp_path: Path) -> None:
    today = datetime.now(UTC)
    ts = today.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    status_path = _make_status_file(tmp_path, updated_at=ts, duration_s=5.0)
    history_path = tmp_path / "history.jsonl"

    _record_current_poll(status_path=status_path, history_path=history_path)
    _record_current_poll(status_path=status_path, history_path=history_path)

    lines = [
        l for l in history_path.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    assert len(lines) == 1


def test_day_labels_are_valid(tmp_path: Path) -> None:
    valid_labels = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    result = get_poll_history_7days(
        status_path=tmp_path / "nonexistent.json",
        history_path=tmp_path / "history.jsonl",
    )
    for entry in result:
        assert entry["day"] in valid_labels
