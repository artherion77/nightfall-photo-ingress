"""Blocklist endpoints."""

from fastapi import APIRouter, Depends
import sqlite3

from api.dependencies import get_registry_connection
from api.auth import verify_api_token
from api.schemas import BlockRuleList
from api.services import BlocklistService

router = APIRouter(prefix="/api/v1", tags=["blocklist"])


@router.get("/blocklist", response_model=BlockRuleList)
async def get_blocklist(
    _: str = Depends(verify_api_token),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> BlockRuleList:
    """Get all blocklist rules."""
    service = BlocklistService(conn)
    return service.get_blocklist()
