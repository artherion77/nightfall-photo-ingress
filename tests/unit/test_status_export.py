"""Status export tests for Module 8."""

from __future__ import annotations

import json
from pathlib import Path

from nightfall_photo_ingress import __version__
from nightfall_photo_ingress.status import write_status_snapshot


def test_status_snapshot_writer_creates_atomic_json(tmp_path: Path) -> None:
    status_path = tmp_path / "run" / "nightfall-status.d" / "photo-ingress.json"

    written_path = write_status_snapshot(
        state="healthy",
        command="poll",
        success=True,
        details={"candidate_count": 3},
        status_path=status_path,
    )

    assert written_path == status_path
    assert status_path.exists()
    assert not status_path.with_suffix(".json.tmp").exists()

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["service"] == "photo-ingress"
    assert payload["version"] == __version__
    assert payload["host"]
    assert payload["state"] == "healthy"
    assert payload["command"] == "poll"
    assert payload["success"] is True
    assert payload["details"] == {"candidate_count": 3}


def test_status_snapshot_writer_replaces_existing_file(tmp_path: Path) -> None:
    status_path = tmp_path / "status.json"
    status_path.write_text('{"state":"old"}', encoding="utf-8")

    write_status_snapshot(
        state="degraded",
        command="config-check",
        success=False,
        details={"errors": ["broken"]},
        status_path=status_path,
    )

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["state"] == "degraded"
    assert payload["command"] == "config-check"
    assert payload["success"] is False
    assert payload["details"] == {"errors": ["broken"]}
