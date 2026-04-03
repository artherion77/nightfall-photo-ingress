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
