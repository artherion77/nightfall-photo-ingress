"""Bearer token authentication dependency for FastAPI."""

from datetime import UTC, datetime
import hmac
import json
import sqlite3

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nightfall_photo_ingress.config import AppConfig

from api.dependencies import get_app_config

_security = HTTPBearer(auto_error=False)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_auth_failure_audit(
    request: Request,
    *,
    status_code: int,
    detail: str,
) -> None:
    """Persist a structured auth-failure audit row when possible."""

    conn: sqlite3.Connection | None = getattr(request.app.state, "registry_conn", None)
    if conn is None:
        return

    client_ip = request.client.host if request.client else "unknown"
    details = json.dumps(
        {
            "path": str(request.url.path),
            "method": request.method,
            "client_ip": client_ip,
            "status_code": status_code,
            "detail": detail,
        }
    )

    conn.execute(
        """
        INSERT INTO audit_log (sha256, account_name, action, reason, details_json, actor, ts)
        VALUES (?, NULL, ?, ?, ?, ?, ?)
        """,
        (
            "auth_failure",
            "auth_failure",
            detail,
            details,
            "api_auth",
            _utc_now_iso(),
        ),
    )
    conn.commit()


def _raise_auth_error(request: Request, *, status_code: int, detail: str) -> None:
    _write_auth_failure_audit(request, status_code=status_code, detail=detail)
    raise HTTPException(
        status_code=status_code,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


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
        _raise_auth_error(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    
    if credentials.scheme.lower() != "bearer":
        _raise_auth_error(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
        )
    
    if not app_config.web.api_token:
        _raise_auth_error(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token not configured",
        )
    
    if not hmac.compare_digest(credentials.credentials, app_config.web.api_token):
        _raise_auth_error(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    
    _ = request
    return credentials.credentials
