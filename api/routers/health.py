"""Health check endpoints."""

import subprocess
import sys

from fastapi import APIRouter, Depends, HTTPException
from nightfall_photo_ingress.config import AppConfig

from api.auth import verify_api_token
from api.dependencies import get_app_config, get_config_path
from api.schemas import HealthResponse
from api.schemas.health import PollHistoryEntry, PollTriggerResponse
from api.services import HealthService
from api.services.health_service import get_poller_status
from api.services.poll_history import get_poll_history_7days

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(
    _: str = Depends(verify_api_token),
    app_config: AppConfig = Depends(get_app_config),
) -> HealthResponse:
    """Get current health status."""
    return HealthService.get_health(
        poll_interval_minutes=app_config.core.poll_interval_minutes,
        poll_lock_path=app_config.core.registry_path.with_suffix(".poll.lock"),
    )


@router.post("/poll/trigger", response_model=PollTriggerResponse, status_code=202)
async def trigger_poll(
    _: str = Depends(verify_api_token),
    app_config: AppConfig = Depends(get_app_config),
    config_path: str = Depends(get_config_path),
) -> PollTriggerResponse:
    """Trigger an immediate poll cycle in the background."""
    if (
        get_poller_status(
            lock_path=app_config.core.registry_path.with_suffix(".poll.lock"),
        )
        == "in_progress"
    ):
        raise HTTPException(status_code=409, detail="Poll already in progress")
    subprocess.Popen(
        [sys.executable, "-m", "nightfall_photo_ingress", "poll",
         "--path", config_path],
        close_fds=True,
        start_new_session=True,
    )
    return PollTriggerResponse(status="accepted")


@router.get("/health/poll-history", response_model=list[PollHistoryEntry])
async def get_poll_history(
    _: str = Depends(verify_api_token),
) -> list[PollHistoryEntry]:
    """Return last 7 days of poll duration history (oldest first, missing days = 0)."""
    entries = get_poll_history_7days()
    return [PollHistoryEntry(**e) for e in entries]
