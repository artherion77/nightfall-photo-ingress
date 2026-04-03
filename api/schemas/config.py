"""Pydantic schemas for effective config endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EffectiveConfig(BaseModel):
    """Effective runtime configuration."""

    config_version: int
    poll_interval_minutes: int
    registry_path: str
    staging_path: str
    pending_path: str
    accepted_path: str
    rejected_path: str
    trash_path: str
    storage_template: str
    accepted_storage_template: str
    verify_sha256_on_first_download: bool
    max_downloads_per_poll: int
    max_poll_runtime_seconds: int
    kpi_thresholds: dict = Field(default_factory=dict)
    api_token: str = "[redacted]"
