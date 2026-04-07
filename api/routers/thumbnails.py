"""Thumbnail serving endpoints."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, status
from fastapi.responses import Response

from api.auth import verify_api_token
from api.dependencies import get_registry_connection, get_thumbnail_cache_path
from api.services.thumbnail_service import (
    ThumbnailGenerationError,
    ThumbnailNotFoundError,
    ThumbnailService,
)

router = APIRouter(prefix="/api/v1", tags=["thumbnails"])


@router.get("/thumbnails/{sha256}")
async def get_thumbnail(
    sha256: Annotated[str, ApiPath(min_length=1, max_length=128)],
    _: str = Depends(verify_api_token),
    conn: sqlite3.Connection = Depends(get_registry_connection),
    cache_root: Path = Depends(get_thumbnail_cache_path),
) -> Response:
    """Serve a cached or lazily-generated thumbnail for a pending item."""

    service = ThumbnailService(conn, cache_root)

    try:
        content = service.get_or_generate(sha256)
    except ThumbnailNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ThumbnailGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Thumbnail generation failed",
        ) from exc

    headers = {
        "Cache-Control": "private, max-age=86400, immutable",
        "ETag": f'"thumb-{sha256}"',
    }
    return Response(content=content, media_type="image/webp", headers=headers)