"""Health check endpoints."""

from fastapi import APIRouter, Depends
from nightfall_photo_ingress.config import AppConfig

from api.auth import verify_api_token
from api.schemas import HealthResponse
from api.services import HealthService

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(
    _: str = Depends(verify_api_token),
) -> HealthResponse:
    """Get current health status."""
    return HealthService.get_health()
