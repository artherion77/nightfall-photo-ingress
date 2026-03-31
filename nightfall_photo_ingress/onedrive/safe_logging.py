"""Centralized log sanitization for OneDrive adapter events.

V2-2 scope:
- Provide one guaranteed sanitization path before emitting structured log fields.
- Redact URL/token-like values recursively across nested dict/list payloads.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .errors import redact_token, redact_url

_TOKEN_KEY_RE = re.compile(
    r"(token|secret|authorization|auth|password|sig|tempauth|client_secret)",
    re.IGNORECASE,
)
_URL_VALUE_RE = re.compile(r"^https?://", re.IGNORECASE)


def sanitize_for_log(value: Any, *, key_hint: str | None = None) -> Any:
    """Return a log-safe value.

    Rules:
    - URL-looking strings are passed through ``redact_url``.
    - Token-like keys always redact string values with ``redact_token``.
    - Dictionaries and lists are sanitized recursively.
    - ``Path`` values are converted to strings.
    - Unsupported objects fall back to ``str(value)``.
    """

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, str):
        if key_hint and _TOKEN_KEY_RE.search(key_hint):
            return redact_token(value)
        if _URL_VALUE_RE.match(value):
            return redact_url(value)
        return value

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            key_str = str(key)
            sanitized[key_str] = sanitize_for_log(nested, key_hint=key_str)
        return sanitized

    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_log(item, key_hint=key_hint) for item in value]

    return str(value)


def sanitize_extra(extra: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized shallow copy of a logging ``extra`` payload."""

    return {str(key): sanitize_for_log(value, key_hint=str(key)) for key, value in extra.items()}
