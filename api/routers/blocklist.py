"""Blocklist endpoints."""

from fastapi import APIRouter, Depends, Request
import sqlite3

from api.auth import verify_api_token
from api.schemas import BlockRuleList
from api.services import BlocklistService

router = APIRouter(prefix="/api/v1", tags=["blocklist"])


def get_registry_connection(request: Request) -> sqlite3.Connection:
    """Get registry connection from app state."""
    import api.app
    if api.app._registry_conn is None:
        raise RuntimeError("Registry connection not initialized")
    return api.app._registry_conn


@router.get("/blocklist", response_model=BlockRuleList)
async def get_blocklist(
    _: str = Depends(verify_api_token),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> BlockRuleList:
    """Get all blocklist rules."""
    service = BlocklistService(conn)
    return service.get_blocklist()
