"""Staging queue endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Request
import sqlite3

from api.auth import verify_api_token
from api.schemas import StagingPage, StagingItem
from api.services import StagingService

router = APIRouter(prefix="/api/v1", tags=["staging"])


def get_registry_connection(request: Request) -> sqlite3.Connection:
    """Get registry connection from app state."""
    import api.app
    if api.app._registry_conn is None:
        raise RuntimeError("Registry connection not initialized")
    return api.app._registry_conn


@router.get("/staging", response_model=StagingPage)
async def get_staging(
    _: str = Depends(verify_api_token),
    limit: int = 20,
    after: str | None = None,
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> StagingPage:
    """Get paginated pending items."""
    service = StagingService(conn)
    return service.get_staging_items(limit=min(limit, 100), after_cursor=after)


@router.get("/items/{item_id}", response_model=StagingItem)
async def get_item(
    item_id: str,
    _: str = Depends(verify_api_token),
    conn: sqlite3.Connection = Depends(get_registry_connection),
) -> StagingItem:
    """Get single item detail."""
    service = StagingService(conn)
    item = service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item
