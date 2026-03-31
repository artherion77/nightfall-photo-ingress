"""Retry policy and back-off computation for the OneDrive adapter.

Centralises retry decision logic so it can be tested independently of real
network I/O and injected as a deterministic stub when testing higher-level
components.

Chunk 2 deliverables:
- RETRYABLE_STATUS_CODES: canonical set covering 429 / 5xx transient codes.
- RetryPolicy: immutable policy value object.
- classify_status: single authoritative decision on whether to retry a status.
- parse_retry_after: RFC 7231-compliant header parser with safe fallbacks.
- compute_delay: capped exponential back-off with optional server hint and jitter.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

# ---------------------------------------------------------------------------
# Retryable status set
# ---------------------------------------------------------------------------

# 429 = Too Many Requests (rate limiting).
# 500 / 502 / 503 / 504 = transient infrastructure errors worth retrying.
# 400/401/403/404 and other 4xx codes are not transient and are NOT retried.
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


# ---------------------------------------------------------------------------
# Policy value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """Immutable retry and back-off configuration.

    Attributes:
        max_attempts: Total number of attempts including the first try.
                      A value of 1 means no retries (fail immediately).
        base_delay:   Initial back-off interval in seconds for exponential
                      back-off when no server-supplied hint is available.
        max_delay:    Upper cap on any computed sleep duration, in seconds.
    """

    max_attempts: int = 4
    base_delay: float = 1.0
    max_delay: float = 60.0


#: Shared default policy.  Callers with different requirements pass their own.
DEFAULT_POLICY: RetryPolicy = RetryPolicy()


# ---------------------------------------------------------------------------
# Decision and computation helpers
# ---------------------------------------------------------------------------


def classify_status(status_code: int) -> bool:
    """Return ``True`` if *status_code* is a transient condition worth retrying.

    Only codes listed in :data:`RETRYABLE_STATUS_CODES` are considered
    transient.  Client errors (4xx, except 429) and responses whose meaning
    has no retry semantics are returned as ``False``.
    """
    return status_code in RETRYABLE_STATUS_CODES


def parse_retry_after(header_value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value to a wait duration in seconds.

    Handles all forms encountered in production Microsoft Graph responses:

    * ``None`` or empty string → ``None`` (caller falls back to computed delay).
    * Numeric seconds string → ``float``, clamped to ≥ 0.
    * HTTP-date string (RFC 7231 format) → seconds from now, clamped to ≥ 0.
    * Any malformed or unrecognised string → ``None``.

    The caller is responsible for capping the returned value against
    ``RetryPolicy.max_delay``.  This function never raises.
    """
    if not header_value:
        return None

    stripped = header_value.strip()
    if not stripped:
        return None

    # Attempt 1: simple decimal-seconds string (e.g. "60", "0", "1.5").
    try:
        return max(0.0, float(stripped))
    except ValueError:
        pass

    # Attempt 2: RFC 7231 HTTP-date (e.g. "Mon, 01 Apr 2026 12:00:00 GMT").
    try:
        retry_dt = parsedate_to_datetime(stripped)
        now = datetime.now(timezone.utc)
        delta = (retry_dt - now).total_seconds()
        return max(0.0, delta)
    except Exception:  # noqa: BLE001  – any parse failure is safe to discard
        return None


def compute_delay(
    attempt: int,
    retry_after: float | None,
    policy: RetryPolicy,
    jitter_fn: Callable[[], float] | None = None,
) -> float:
    """Compute the sleep duration before the next retry attempt.

    Priority order:

    1. Server-supplied ``Retry-After`` value (capped at ``policy.max_delay``).
    2. Capped exponential back-off with optional jitter when no server hint.

    Args:
        attempt:    1-based index of the attempt that just failed.
        retry_after: Parsed server hint in seconds, or ``None``.
        policy:     Active retry policy supplying base, cap, and attempt limits.
        jitter_fn:  Zero-argument callable returning a non-negative jitter value
                    in seconds.  Defaults to ``random.uniform(0, 1)``.  Pass
                    ``lambda: 0.0`` in unit tests for fully deterministic results.

    Returns:
        Seconds to sleep, always ``<= policy.max_delay``.
    """
    if retry_after is not None:
        # Honour the server's guidance but respect our own cap.
        return min(retry_after, policy.max_delay)

    # Exponential back-off: base_delay * 2^(attempt-1).
    backoff = policy.base_delay * (2 ** (attempt - 1))
    jitter = jitter_fn() if jitter_fn is not None else random.uniform(0.0, 1.0)
    return min(backoff + jitter, policy.max_delay)
