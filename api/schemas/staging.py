"""Pydantic schemas for staging endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class StagingItem(BaseModel):
    """Single pending item in the staging queue."""

    sha256: str
    filename: str
    size_bytes: int
    first_seen_at: str
    updated_at: str
    account: str | None = None
    onedrive_id: str | None = None


class StagingPage(BaseModel):
    """Paginated list of pending items."""

    items: list[StagingItem]
    cursor: str | None = None
    has_more: bool
    total: int
