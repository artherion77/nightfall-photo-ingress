"""Configuration endpoints."""

from fastapi import APIRouter, Depends, Request
from nightfall_photo_ingress.config import AppConfig

from api.auth import verify_api_token
from api.schemas import EffectiveConfig
from api.services import ConfigService

router = APIRouter(prefix="/api/v1", tags=["config"])


def get_app_config(request: Request) -> AppConfig:
    """Get app config from app state."""
    import api.app
    if api.app._app_config is None:
        raise RuntimeError("App config not initialized")
    return api.app._app_config


@router.get("/config/effective", response_model=EffectiveConfig)
async def get_effective_config(
    _: str = Depends(verify_api_token),
    app_config: AppConfig = Depends(get_app_config),
) -> EffectiveConfig:
    """Get effective configuration."""
    return ConfigService.get_effective_config(app_config)
