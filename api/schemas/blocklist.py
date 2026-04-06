"""Pydantic schemas for blocklist endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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

    pattern: str = Field(min_length=1, max_length=512)
    rule_type: Literal["filename", "regex"]
    reason: str | None = Field(default=None, max_length=512)
    enabled: bool = True


class BlockRuleUpdate(BaseModel):
    """Partial update payload for a blocklist rule."""

    pattern: str | None = Field(default=None, min_length=1, max_length=512)
    rule_type: Literal["filename", "regex"] | None = None
    reason: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None


class BlockRuleDeleteResponse(BaseModel):
    """Delete response payload for blocklist rules."""

    id: int
    deleted: bool
