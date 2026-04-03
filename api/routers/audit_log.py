"""Audit log endpoints."""

from fastapi import APIRouter, Depends
import sqlite3

from api.dependencies import get_registry_connection
from api.auth import verify_api_token
from api.schemas import AuditPage
from api.services import AuditService

router = APIRouter(prefix="/api/v1", tags=["audit"])


@router.get("/audit-log", response_model=AuditPage)
async def get_audit_log(
    _: str = Depends(verify_api_token),
    limit: int = 50,
    after: str | None = None,
    action: str | None = None,
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> AuditPage:
    """Get paginated audit events."""
    service = AuditService(conn)
    return service.get_audit_log(
        limit=min(limit, 1000),
        after_cursor=after,
        action_filter=action,
    )
