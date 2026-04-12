"""Pydantic schemas for audit endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class AuditEvent(BaseModel):
    """Single audit log event."""

    id: int
    sha256: str | None = None
    account_name: str | None = None
    client_ip: str | None = None
    action: str
    description: str
    reason: str | None = None
    filename: str | None = None
    details: dict | None = None
    actor: str
    ts: str


class AuditPage(BaseModel):
    """Paginated list of audit events."""

    events: list[AuditEvent]
    cursor: str | None = None
    has_more: bool


class AuditDailySummary(BaseModel):
    """Current-day accepted/rejected outcome counts derived from audit events."""

    day_utc: str
    accepted_today: int
    rejected_today: int
