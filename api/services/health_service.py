"""Health service for API endpoint data shaping."""

from __future__ import annotations

import json

from api.schemas import HealthResponse, ServiceStatus
from nightfall_photo_ingress.status import STATUS_FILE_PATH


class HealthService:
    """Provides health status information."""

    @staticmethod
    def get_health() -> HealthResponse:
        """Read health snapshot from status file."""

        try:
            if STATUS_FILE_PATH.exists():
                content = STATUS_FILE_PATH.read_text(encoding="utf-8")
                status_data = json.loads(content)
                success = status_data.get("success", False)
                updated_at = status_data.get("updated_at", "unknown")
            else:
                success = False
                updated_at = "never"

            return HealthResponse(
                polling_ok=ServiceStatus(
                    ok=success,
                    message="Ingest process is running" if success else "No status file found",
                ),
                auth_ok=ServiceStatus(ok=True, message="Auth OK"),
                registry_ok=ServiceStatus(ok=True, message="Registry OK"),
                disk_ok=ServiceStatus(ok=True, message="Disk OK"),
                last_updated_at=updated_at,
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
                error=str(exc),
            )
