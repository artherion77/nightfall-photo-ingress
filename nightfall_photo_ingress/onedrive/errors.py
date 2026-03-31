"""Structured error taxonomy for the OneDrive adapter.

Chunk 1 scope:
- Centralise all adapter exceptions in one place.
- Carry structured, loggable fields without leaking sensitive data.
- Provide URL/token redaction utilities used by every raise site.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# URL / token redaction
# ---------------------------------------------------------------------------

# Query-string parameters that commonly carry raw secret material in
# pre-authenticated OneDrive/SharePoint download URLs.
_SECRET_PARAMS = re.compile(
    r"(tempauth|sig|sv|se|st|spr|srt|ss|sp|sas|X-Amz-Security-Token"
    r"|access_token|token|client_secret)=[^&]*",
    re.IGNORECASE,
)


def redact_url(url: str) -> str:
    """Return a log-safe representation of *url*.

    Rules applied in order:
    1. If the URL contains a query string, strip it entirely.  Pre-authenticated
       download URLs embed secrets in query parameters; removing them prevents
       accidental leakage via logs, exception messages, or tracebacks.
    2. Truncate netloc+path to at most 80 chars so stack traces remain readable.
    3. Never raise – if parsing fails, return a fixed sentinel.

    Examples::

        >>> redact_url("https://me.sharepoint.com/…?tempauth=abc123&ts=1")
        'https://me.sharepoint.com/… [query redacted]'

        >>> redact_url("https://graph.microsoft.com/v1.0/me/drive/root:/delta")
        'https://graph.microsoft.com/v1.0/me/drive/root:/delta'
    """
    if not url:
        return "<empty-url>"
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return "<unparseable-url>"

    if parsed.query:
        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if len(base) > 80:
            base = base[:77] + "…"
        return f"{base} [query redacted]"

    safe = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if len(safe) > 120:
        safe = safe[:117] + "…"
    return safe


def redact_token(token: str) -> str:
    """Return a log-safe representation of an access token.

    Shows only prefix and length so the log entry is identifiable without
    exposing the full credential.
    """
    if not token:
        return "<empty-token>"
    prefix = token[:6] if len(token) >= 6 else token
    return f"{prefix}…[{len(token)} chars]"


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class OneDriveAdapterError(RuntimeError):
    """Base class for all OneDrive adapter errors.

    Attributes:
        code:        Machine-readable error code for programmatic handling.
        account:     Account name (if known at raise site).
        operation:   Short description of the operation that failed.
        status_code: HTTP status code if the failure originated from an HTTP
                     response, else None.
        safe_hint:   A log-safe, non-sensitive hint for the operator.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "adapter_error",
        account: str | None = None,
        operation: str | None = None,
        status_code: int | None = None,
        safe_hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.account = account
        self.operation = operation
        self.status_code = status_code
        self.safe_hint = safe_hint or message

    def as_log_dict(self) -> dict[str, object]:
        """Return a structured dict suitable for structured logging."""
        return {
            "error_code": self.code,
            "account": self.account,
            "operation": self.operation,
            "status_code": self.status_code,
            "hint": self.safe_hint,
        }


class AuthError(OneDriveAdapterError):
    """Raised when authentication cannot produce a usable token.

    Examples: no cached account, device-code flow failure, token extraction
    failure, corrupted/unreadable cache.
    """

    def __init__(self, message: str, *, account: str | None = None, **kwargs: object) -> None:
        super().__init__(
            message,
            code=kwargs.pop("code", "auth_error"),  # type: ignore[arg-type]
            account=account,
            operation=kwargs.pop("operation", "auth"),  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )


class GraphError(OneDriveAdapterError):
    """Raised for non-recoverable or unclassified Graph API failures.

    The *url* parameter is always redacted before storage; never pass a raw
    pre-authenticated URL as the human-visible *message*.
    """

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        **kwargs: object,
    ) -> None:
        # Redact URL immediately so it never surfaces in str(exc) or tracebacks.
        self.safe_url = redact_url(url) if url else None
        hint = kwargs.pop("safe_hint", None) or (  # type: ignore[assignment]
            f"Graph request failed at {self.safe_url}" if self.safe_url else message
        )
        super().__init__(
            message,
            code=kwargs.pop("code", "graph_error"),  # type: ignore[arg-type]
            operation=kwargs.pop("operation", "graph_request"),  # type: ignore[arg-type]
            safe_hint=hint,
            **kwargs,  # type: ignore[arg-type]
        )


class GraphThrottleError(GraphError):
    """Raised when Graph signals throttling (429) or temporary unavailability (503).

    Carries ``retry_after_seconds`` for callers that implement backoff logic.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(message, code="graph_throttle", **kwargs)
        self.retry_after_seconds = retry_after_seconds


class GraphResyncRequired(GraphError):
    """Raised when Graph returns 410 Gone, signalling a required delta resync.

    The ``resync_url`` attribute holds the Location header value from the 410
    response if provided.  Callers must discard the current cursor and initiate
    a full re-crawl.
    """

    def __init__(
        self,
        message: str,
        *,
        resync_url: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(message, code="graph_resync_required", **kwargs)
        # Store safely – Location header is not pre-authenticated but keep tidy.
        self.resync_url = resync_url


class DownloadError(GraphError):
    """Raised for failures specific to file content download.

    Distinguishes content retrieval failures from metadata/API failures so
    callers can apply targeted retry and quarantine policies.
    """

    def __init__(self, message: str, *, item_id: str | None = None, **kwargs: object) -> None:
        super().__init__(message, code=kwargs.pop("code", "download_error"), **kwargs)  # type: ignore[arg-type]
        self.item_id = item_id


class GhostItemError(DownloadError):
    """Raised when an item appears in a delta feed but cannot be downloaded.

    Causes: expired /missing downloadUrl, repeated 404 after URL re-resolve,
    item deleted since delta page was fetched.
    """

    def __init__(self, message: str, *, item_id: str | None = None, **kwargs: object) -> None:
        super().__init__(message, code="ghost_item", item_id=item_id, **kwargs)
