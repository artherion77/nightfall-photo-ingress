"""Schemas for API endpoints."""

from pydantic import BaseModel, Field
from typing import Optional


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
    error: Optional[str] = None


class StagingItem(BaseModel):
    """Single pending item in the staging queue."""

    sha256: str
    filename: str
    size_bytes: int
    first_seen_at: str
    updated_at: str
    account: Optional[str] = None
    onedrive_id: Optional[str] = None


class StagingPage(BaseModel):
    """Paginated list of pending items."""

    items: list[StagingItem]
    cursor: Optional[str] = None
    has_more: bool
    total: int


class AuditEvent(BaseModel):
    """Single audit log event."""

    id: int
    sha256: Optional[str] = None
    account_name: Optional[str] = None
    action: str
    reason: Optional[str] = None
    details: Optional[dict] = None
    actor: str
    ts: str


class AuditPage(BaseModel):
    """Paginated list of audit events."""

    events: list[AuditEvent]
    cursor: Optional[str] = None
    has_more: bool


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


class BlockRule(BaseModel):
    """Single blocklist rule."""

    id: int
    pattern: str
    rule_type: str
    reason: Optional[str] = None
    enabled: bool
    created_at: str
    updated_at: str


class BlockRuleList(BaseModel):
    """List of blocklist rules."""

    rules: list[BlockRule]
