"""Bearer token authentication dependency for FastAPI."""

from datetime import UTC, datetime
import hmac
import json
import sqlite3
from time import monotonic

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nightfall_photo_ingress.config import AppConfig

from api.dependencies import get_app_config

_security = HTTPBearer(auto_error=False)
_AUTH_FAILURE_AUDIT_WINDOW_SECONDS = 60.0
_AUTH_FAILURE_AUDIT_MAX_KEYS = 1024


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_auth_failure_path(path: str) -> str:
    if path.startswith("/api/v1/thumbnails/"):
        return "/api/v1/thumbnails/{sha256}"
    return path


def _should_audit_auth_failure(
    request: Request,
    *,
    client_ip: str,
    status_code: int,
    detail: str,
) -> bool:
    now = monotonic()
    rate_limit_state: dict[tuple[str, str, str, int, str], float] | None = getattr(
        request.app.state,
        "auth_failure_audit_rate_limit",
        None,
    )
    if rate_limit_state is None:
        rate_limit_state = {}
        request.app.state.auth_failure_audit_rate_limit = rate_limit_state

    if len(rate_limit_state) >= _AUTH_FAILURE_AUDIT_MAX_KEYS:
        expired_keys = [
            key
            for key, last_seen in rate_limit_state.items()
            if now - last_seen >= _AUTH_FAILURE_AUDIT_WINDOW_SECONDS
        ]
        for key in expired_keys:
            rate_limit_state.pop(key, None)

    key = (
        client_ip,
        request.method,
        _normalize_auth_failure_path(str(request.url.path)),
        status_code,
        detail,
    )
    last_seen = rate_limit_state.get(key)
    if last_seen is not None and now - last_seen < _AUTH_FAILURE_AUDIT_WINDOW_SECONDS:
        return False

    rate_limit_state[key] = now
    return True


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
    if not _should_audit_auth_failure(
        request,
        client_ip=client_ip,
        status_code=status_code,
        detail=detail,
    ):
        return

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
