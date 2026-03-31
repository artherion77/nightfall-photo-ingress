"""Dedicated tests for V2-2 centralized safe log sanitizer."""

from __future__ import annotations

import json
import logging

from nightfall_photo_ingress.logging_bootstrap import JsonFormatter
from nightfall_photo_ingress.adapters.onedrive.safe_logging import sanitize_extra, sanitize_for_log


def test_sanitize_for_log_redacts_nested_url_and_tokens() -> None:
    """Nested payload values should be recursively sanitized."""

    payload = {
        "download_url": "https://files.example/path?sig=abc&token=xyz",
        "auth": {
            "access_token": "abcdef1234567890",
            "nested": [
                "https://graph.microsoft.com/v1.0/me/drive/root:/x:/delta?tempauth=aaa",
                {"client_secret": "super-secret"},
            ],
        },
    }

    sanitized = sanitize_for_log(payload)

    assert isinstance(sanitized, dict)
    assert sanitized["download_url"].endswith("[query redacted]")
    assert "sig=" not in sanitized["download_url"]

    auth = sanitized["auth"]
    assert auth["access_token"].endswith("chars]")
    assert "abcdef1234567890" not in auth["access_token"]
    assert auth["nested"][0].endswith("[query redacted]")
    assert auth["nested"][1]["client_secret"].endswith("chars]")


def test_sanitize_extra_produces_log_safe_dict() -> None:
    """sanitize_extra should sanitize all values while preserving keys."""

    payload = {
        "event": "graph_request_attempt_start",
        "url": "https://graph.microsoft.com/v1.0/me?access_token=raw",
        "authorization": "Bearer super-token",
        "attempt": 1,
    }

    sanitized = sanitize_extra(payload)

    assert set(sanitized.keys()) == set(payload.keys())
    assert sanitized["url"].endswith("[query redacted]")
    assert "access_token=" not in sanitized["url"]
    assert sanitized["authorization"].endswith("chars]")


def test_json_formatter_with_sanitized_extra_never_leaks_raw_values() -> None:
    """Regression: JSON formatter output should not contain unsanitized secrets."""

    logger = logging.getLogger("chunk2.safe.formatter")
    record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="onedrive_trace",
        args=(),
        exc_info=None,
        extra=sanitize_extra(
            {
                "event": "download_attempt_start",
                "download_url": "https://files.example/content?sig=secret&token=abc",
                "access_token": "very-secret-token",
            }
        ),
    )

    rendered = JsonFormatter().format(record)
    payload = json.loads(rendered)

    assert payload["download_url"].endswith("[query redacted]")
    assert "sig=" not in payload["download_url"]
    assert "token=" not in payload["download_url"]
    assert payload["access_token"].endswith("chars]")
    assert "very-secret-token" not in rendered
