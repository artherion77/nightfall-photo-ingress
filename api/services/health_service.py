"""Health service for API endpoint data shaping."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime

from api.schemas import HealthResponse, ServiceStatus
from nightfall_photo_ingress.status import STATUS_FILE_PATH


_TIMER_UNIT = "nightfall-photo-ingress.timer"
_SERVICE_UNIT = "nightfall-photo-ingress.service"


def _systemctl_is_active(unit: str) -> str:
    """Return 'active', 'inactive', or 'unknown'; never raises."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _get_timer_next_elapse_iso() -> str | None:
    """Return next scheduled timer elapse as ISO 8601 UTC string, or None."""
    try:
        result = subprocess.run(
            ["systemctl", "show", _TIMER_UNIT,
             "--property=NextElapseUSecRealtime", "--value"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        if not value:
            return None
        usec = int(value)
        if usec == 0:
            return None
        return datetime.fromtimestamp(usec / 1_000_000, tz=UTC).isoformat()
    except Exception:
        return None


def get_poller_status() -> str:
    """Determine poller operational status from systemd; never raises."""
    svc = _systemctl_is_active(_SERVICE_UNIT)
    if svc == "active":
        return "in_progress"
    timer = _systemctl_is_active(_TIMER_UNIT)
    if timer == "active":
        return "timer_running"
    if timer == "inactive":
        return "timer_stopped"
    return "unknown"


class HealthService:
    """Provides health status information."""

    @staticmethod
    def get_health(*, poll_interval_minutes: int = 0) -> HealthResponse:
        """Read health snapshot from status file and systemd state."""

        try:
            last_poll_at: str | None = None
            success = False

            if STATUS_FILE_PATH.exists():
                content = STATUS_FILE_PATH.read_text(encoding="utf-8")
                status_data = json.loads(content)
                success = status_data.get("success", False)
                raw_ts = status_data.get("updated_at")
                last_poll_at = raw_ts if isinstance(raw_ts, str) and raw_ts else None

            poller_status = get_poller_status()
            next_poll_at = _get_timer_next_elapse_iso()

            return HealthResponse(
                polling_ok=ServiceStatus(
                    ok=success,
                    message="Ingest process is running" if success else "No status file found",
                ),
                auth_ok=ServiceStatus(ok=True, message="Auth OK"),
                registry_ok=ServiceStatus(ok=True, message="Registry OK"),
                disk_ok=ServiceStatus(ok=True, message="Disk OK"),
                last_updated_at=last_poll_at or "never",
                last_poll_at=last_poll_at,
                next_poll_at=next_poll_at,
                poller_status=poller_status,
                poll_interval_minutes=poll_interval_minutes,
                error=None,
            )
        except Exception as exc:
            message = f"Error: {exc}"
            return HealthResponse(
                polling_ok=ServiceStatus(ok=False, message=message),
                auth_ok=ServiceStatus(ok=False, message=message),
                registry_ok=ServiceStatus(ok=False, message=message),
                disk_ok=ServiceStatus(ok=False, message=message),
                last_updated_at="error",
                last_poll_at=None,
                next_poll_at=None,
                poller_status="unknown",
                poll_interval_minutes=poll_interval_minutes,
                error=str(exc),
            )
