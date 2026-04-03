"""Configuration endpoints."""

from fastapi import APIRouter, Depends
from nightfall_photo_ingress.config import AppConfig

from api.dependencies import get_app_config
from api.auth import verify_api_token
from api.schemas import EffectiveConfig
from api.services import ConfigService

router = APIRouter(prefix="/api/v1", tags=["config"])


@router.get("/config/effective", response_model=EffectiveConfig)
async def get_effective_config(
    _: str = Depends(verify_api_token),
    app_config: AppConfig = Depends(get_app_config),
) -> EffectiveConfig:
    """Get effective configuration."""
    return ConfigService.get_effective_config(app_config)
