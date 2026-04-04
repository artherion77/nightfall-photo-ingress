"""Pydantic schemas for blocklist endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class BlockRule(BaseModel):
    """Single blocklist rule."""

    id: int
    pattern: str
    rule_type: str
    reason: str | None = None
    enabled: bool
    created_at: str
    updated_at: str


class BlockRuleList(BaseModel):
    """List of blocklist rules."""

    rules: list[BlockRule]


class BlockRuleCreate(BaseModel):
    """Create payload for a blocklist rule."""

    pattern: str
    rule_type: str
    reason: str | None = None
    enabled: bool = True


class BlockRuleUpdate(BaseModel):
    """Partial update payload for a blocklist rule."""

    pattern: str | None = None
    rule_type: str | None = None
    reason: str | None = None
    enabled: bool | None = None


class BlockRuleDeleteResponse(BaseModel):
    """Delete response payload for blocklist rules."""

    id: int
    deleted: bool
