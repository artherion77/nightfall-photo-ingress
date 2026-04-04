"""Bearer token authentication dependency for FastAPI."""

import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nightfall_photo_ingress.config import AppConfig

from api.dependencies import get_app_config

_security = HTTPBearer(auto_error=False)


async def verify_api_token(
    request: Request,
    app_config: AppConfig = Depends(get_app_config),
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
    
    if not hmac.compare_digest(credentials.credentials, app_config.web.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    _ = request
    return credentials.credentials
