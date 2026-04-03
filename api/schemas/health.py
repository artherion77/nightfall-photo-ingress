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
    error: str | None = None
