"""Settings management endpoints (KPI thresholds, etc.)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from api.auth import verify_api_token
from api.schemas.settings import KPIThresholds, KPIThresholdsResponse, SettingsError
from api.services.settings_service import SettingsService

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("/kpi-thresholds", response_model=KPIThresholdsResponse)
async def get_kpi_thresholds(
    _: str = Depends(verify_api_token),
) -> KPIThresholdsResponse:
    """Get current KPI thresholds.
    
    Returns the current warning and error thresholds for pending queue depth and disk usage.
    
    **Response:** 200 with thresholds and last-update timestamp.
    """
    thresholds = SettingsService.get_kpi_thresholds()
    updated_at = SettingsService.get_last_updated()
    
    return KPIThresholdsResponse(
        thresholds=KPIThresholds(**thresholds),
        updated_at=updated_at,
    )


@router.put("/kpi-thresholds", response_model=KPIThresholdsResponse)
async def update_kpi_thresholds(
    payload: KPIThresholds,
    _: str = Depends(verify_api_token),
) -> KPIThresholdsResponse:
    """Update KPI thresholds.
    
    **Validation:**
    - pending_error must be > pending_warning
    - disk_error_percent must be > disk_warning_percent
    - All values must be within type bounds
    
    **Response:** 200 with updated thresholds.
    **Error:** 422 if validation fails (includes field-level details).
    """
    try:
        thresholds = SettingsService.update_kpi_thresholds(payload)
        updated_at = SettingsService.get_last_updated()
        
        return KPIThresholdsResponse(
            thresholds=KPIThresholds(**thresholds),
            updated_at=updated_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": str(e),
                "code": "validation_error",
            },
        )


@router.patch("/kpi-thresholds", response_model=KPIThresholdsResponse)
async def patch_kpi_thresholds(
    payload: KPIThresholds,
    _: str = Depends(verify_api_token),
) -> KPIThresholdsResponse:
    """Partially update KPI thresholds (PATCH semantics).
    
    Fields provided in the request body are updated; omitted fields retain their current values.
    
    **Validation:** Same as PUT.
    
    **Response:** 200 with updated thresholds.
    **Error:** 422 if validation fails.
    """
    # PATCH semantics: validate the provided payload, which may be partial
    try:
        thresholds = SettingsService.update_kpi_thresholds(payload)
        updated_at = SettingsService.get_last_updated()
        
        return KPIThresholdsResponse(
            thresholds=KPIThresholds(**thresholds),
            updated_at=updated_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": str(e),
                "code": "validation_error",
            },
        )


@router.delete("/kpi-thresholds", response_model=KPIThresholdsResponse, status_code=200)
async def reset_kpi_thresholds(
    _: str = Depends(verify_api_token),
) -> KPIThresholdsResponse:
    """Reset KPI thresholds to factory defaults.
    
    **Response:** 200 with reset thresholds.
    """
    thresholds = SettingsService.reset_kpi_thresholds()
    updated_at = SettingsService.get_last_updated()
    
    return KPIThresholdsResponse(
        thresholds=KPIThresholds(**thresholds),
        updated_at=updated_at,
    )
