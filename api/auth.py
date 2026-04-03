"""Bearer token authentication dependency for FastAPI."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nightfall_photo_ingress.config import AppConfig

_security = HTTPBearer(auto_error=False)


async def verify_api_token(
    app_config: AppConfig = Depends(lambda: getattr(verify_api_token, "_app_config")),
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> str:
    """Verify bearer token from request header against configured api_token.
    
    Raises:
        HTTPException: 401 if token is missing or invalid.
    
    Returns:
        The valid token (for consistency with auth flows).
    """
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not app_config.web.api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token not configured",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if credentials.credentials != app_config.web.api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return credentials.credentials


def set_app_config_for_auth(config: AppConfig) -> None:
    """Store app config in the auth module for dependency resolution."""
    verify_api_token._app_config = config  # type: ignore
