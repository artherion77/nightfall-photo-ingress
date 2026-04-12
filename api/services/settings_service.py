"""Settings service for KPI threshold management."""

from datetime import datetime
from pathlib import Path
from typing import Any

from api.schemas.settings import KPIThresholds


class SettingsService:
    """Service for managing settings like KPI thresholds."""

    # In-memory store for thresholds (Phase 2 MVP; would be persisted to DB in production)
    _thresholds: dict[str, Any] = {
        "pending_warning": 100,
        "pending_error": 500,
        "disk_warning_percent": 80,
        "disk_error_percent": 95,
    }
    _last_updated: str = datetime.utcnow().isoformat() + "Z"

    @classmethod
    def get_kpi_thresholds(cls) -> dict[str, Any]:
        """Get current KPI thresholds."""
        return cls._thresholds.copy()

    @classmethod
    def update_kpi_thresholds(cls, thresholds: KPIThresholds) -> dict[str, Any]:
        """Update KPI thresholds with validation.
        
        Raises:
            ValueError: If validation fails.
        """
        # Validation happens in the Pydantic model
        cls._thresholds = {
            "pending_warning": thresholds.pending_warning,
            "pending_error": thresholds.pending_error,
            "disk_warning_percent": thresholds.disk_warning_percent,
            "disk_error_percent": thresholds.disk_error_percent,
        }
        cls._last_updated = datetime.utcnow().isoformat() + "Z"
        return cls._thresholds.copy()

    @classmethod
    def reset_kpi_thresholds(cls) -> dict[str, Any]:
        """Reset KPI thresholds to defaults."""
        cls._thresholds = {
            "pending_warning": 100,
            "pending_error": 500,
            "disk_warning_percent": 80,
            "disk_error_percent": 95,
        }
        cls._last_updated = datetime.utcnow().isoformat() + "Z"
        return cls._thresholds.copy()

    @classmethod
    def get_last_updated(cls) -> str:
        """Get timestamp of last threshold update."""
        return cls._last_updated
