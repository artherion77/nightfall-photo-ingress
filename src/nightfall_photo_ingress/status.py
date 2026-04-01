"""Status snapshot export for operational health consumers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

STATUS_FILE_PATH = Path("/run/nightfall-status.d/photo-ingress.json")


def write_status_snapshot(
    *,
    state: str,
    command: str,
    success: bool,
    details: dict[str, object] | None = None,
    status_path: Path = STATUS_FILE_PATH,
) -> Path:
    """Write status JSON atomically for health consumers."""

    payload = {
        "service": "photo-ingress",
        "state": state,
        "success": success,
        "command": command,
        "updated_at": datetime.now(UTC).isoformat(),
        "details": details or {},
    }

    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = status_path.with_suffix(status_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp_path.replace(status_path)
    return status_path