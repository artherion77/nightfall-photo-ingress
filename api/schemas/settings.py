"""Pydantic schemas for settings endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class KPIThresholds(BaseModel):
    """KPI threshold values with validation constraints."""

    pending_warning: int = Field(
        default=100,
        ge=1,
        le=9999,
        description="Warning threshold for pending queue item count",
    )
    pending_error: int = Field(
        default=500,
        ge=1,
        le=9999,
        description="Error threshold for pending queue item count",
    )
    disk_warning_percent: int = Field(
        default=80,
        ge=1,
        le=99,
        description="Warning threshold for disk usage percentage",
    )
    disk_error_percent: int = Field(
        default=95,
        ge=1,
        le=99,
        description="Error threshold for disk usage percentage",
    )

    @field_validator("pending_error")
    @classmethod
    def pending_error_must_exceed_warning(cls, v: int, info) -> int:
        """Ensure pending_error > pending_warning."""
        data = info.data
        if "pending_warning" in data and v <= data["pending_warning"]:
            raise ValueError("pending_error must be greater than pending_warning")
        return v

    @field_validator("disk_error_percent")
    @classmethod
    def disk_error_must_exceed_warning(cls, v: int, info) -> int:
        """Ensure disk_error_percent > disk_warning_percent."""
        data = info.data
        if "disk_warning_percent" in data and v <= data["disk_warning_percent"]:
            raise ValueError(
                "disk_error_percent must be greater than disk_warning_percent"
            )
        return v


class KPIThresholdsResponse(BaseModel):
    """Response payload for KPI threshold operations."""

    thresholds: KPIThresholds
    updated_at: str = Field(description="UTC ISO-8601 timestamp of last update")


class SettingsError(BaseModel):
    """Structured error response for settings operations."""

    detail: str = Field(description="Human-readable error message")
    field: str | None = Field(default=None, description="Field that caused the error, if applicable")
    code: str = Field(description="Machine-readable error code")
