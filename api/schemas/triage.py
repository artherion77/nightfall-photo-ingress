"""Pydantic schemas for triage mutation endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class TriageRequest(BaseModel):
    """Optional mutation metadata for triage actions."""

    reason: str | None = None


class TriageResponse(BaseModel):
    """Normalized response for triage mutation calls."""

    action_correlation_id: str
    item_id: str
    state: str
