"""Pydantic schemas for health endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class ServiceStatus(BaseModel):
    """Status of a subsystem."""

    ok: bool
    message: str


class HealthResponse(BaseModel):
    """Health status snapshot."""

    polling_ok: ServiceStatus
    auth_ok: ServiceStatus
    registry_ok: ServiceStatus
    disk_ok: ServiceStatus
    last_updated_at: str
    last_poll_at: str | None = None
    next_poll_at: str | None = None
    poller_status: str = "unknown"
    poll_interval_minutes: int = 0
    error: str | None = None


class PollTriggerResponse(BaseModel):
    """Response from the poll trigger endpoint."""

    status: str
