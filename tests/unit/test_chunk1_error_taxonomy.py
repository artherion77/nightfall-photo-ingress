"""Chunk 1 tests: error taxonomy and URL/token redaction envelope.

Covers:
- redact_url() strips query strings that carry secrets
- redact_url() keeps clean paths intact
- redact_url() handles edge cases (empty, unparseable)
- redact_token() masks token body while preserving prefix+length
- Error classes carry expected structured fields
- Exception messages never expose raw pre-authenticated URLs
- as_log_dict() produces loggable structure without sensitive data
- AuthError raised by auth module carries safe_hint, not raw error description
"""

from __future__ import annotations

import pytest

from nightfall_photo_ingress.adapters.onedrive.errors import (
    AuthError,
    DownloadError,
    GhostItemError,
    GraphError,
    GraphResyncRequired,
    GraphThrottleError,
    OneDriveAdapterError,
    redact_token,
    redact_url,
)


# ---------------------------------------------------------------------------
# redact_url
# ---------------------------------------------------------------------------


class TestRedactUrl:
    """URL redaction strips query strings that carry auth secrets."""

    def test_strips_query_string_with_tempauth(self) -> None:
        url = "https://example-my.sharepoint.com/personal/user/file.jpg?tempauth=SECRET123&ts=1"
        result = redact_url(url)
        assert "SECRET123" not in result
        assert "tempauth" not in result
        assert "[query redacted]" in result

    def test_strips_query_string_with_sig_param(self) -> None:
        url = "https://blob.core.windows.net/container/file?sv=2021&sig=ABCDEF&se=2026"
        result = redact_url(url)
        assert "ABCDEF" not in result
        assert "sig" not in result
        assert "[query redacted]" in result

    def test_preserves_clean_graph_api_url(self) -> None:
        url = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"
        result = redact_url(url)
        # No query string – should be returned with scheme+host+path intact
        assert "graph.microsoft.com" in result
        assert "[query redacted]" not in result

    def test_handles_empty_string(self) -> None:
        assert redact_url("") == "<empty-url>"

    def test_handles_none_like_falsy(self) -> None:
        # Callers must pass str; verify no crash on unusual input
        assert redact_url("") != ""  # just confirms it returns something safe

    def test_truncates_very_long_url_with_query(self) -> None:
        long_path = "/a" * 100
        url = f"https://example.com{long_path}?token=SECRET"
        result = redact_url(url)
        assert "SECRET" not in result
        assert len(result) < 200  # must not explode output

    def test_truncates_very_long_clean_url(self) -> None:
        long_path = "/segment" * 20
        url = f"https://graph.microsoft.com{long_path}"
        result = redact_url(url)
        assert len(result) <= 125  # truncated + ellipsis

    def test_access_token_query_param_stripped(self) -> None:
        url = "https://api.example.com/data?access_token=tok123&foo=bar"
        result = redact_url(url)
        assert "tok123" not in result


# ---------------------------------------------------------------------------
# redact_token
# ---------------------------------------------------------------------------


class TestRedactToken:
    """Token redaction retains prefix and length but hides body."""

    def test_shows_prefix_and_length(self) -> None:
        token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
        result = redact_token(token)
        assert result.startswith("eyJhbG")
        assert str(len(token)) in result
        assert "payload" not in result
        assert "signature" not in result

    def test_handles_empty_token(self) -> None:
        assert redact_token("") == "<empty-token>"

    def test_handles_short_token(self) -> None:
        result = redact_token("abc")
        assert "abc" in result  # short enough that full prefix shown
        assert "3 chars" in result


# ---------------------------------------------------------------------------
# Error class hierarchy and structured fields
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    """All adapter errors derive from OneDriveAdapterError."""

    def test_auth_error_is_adapter_error(self) -> None:
        err = AuthError("test")
        assert isinstance(err, OneDriveAdapterError)

    def test_graph_error_is_adapter_error(self) -> None:
        err = GraphError("test")
        assert isinstance(err, OneDriveAdapterError)

    def test_throttle_error_is_graph_error(self) -> None:
        err = GraphThrottleError("throttled", retry_after_seconds=30.0)
        assert isinstance(err, GraphError)
        assert err.retry_after_seconds == 30.0

    def test_resync_required_is_graph_error(self) -> None:
        err = GraphResyncRequired("gone", resync_url="https://graph.microsoft.com/resync")
        assert isinstance(err, GraphError)
        assert err.resync_url is not None

    def test_download_error_is_graph_error(self) -> None:
        err = DownloadError("failed", item_id="ITEM123")
        assert isinstance(err, GraphError)
        assert err.item_id == "ITEM123"

    def test_ghost_item_is_download_error(self) -> None:
        err = GhostItemError("ghost", item_id="GHOST1")
        assert isinstance(err, DownloadError)
        assert err.code == "ghost_item"


# ---------------------------------------------------------------------------
# Structured fields on errors
# ---------------------------------------------------------------------------


class TestErrorStructuredFields:
    """Errors carry code, account, operation, status_code, safe_hint."""

    def test_graph_error_with_url_does_not_expose_url_in_message(self) -> None:
        raw_url = "https://example.sharepoint.com/file?tempauth=SUPERSECRET"
        err = GraphError("request failed", url=raw_url, status_code=429)
        # The primary exception message must not expose the raw URL
        assert "SUPERSECRET" not in str(err)
        assert "SUPERSECRET" not in (err.safe_hint or "")

    def test_graph_error_safe_url_is_redacted(self) -> None:
        raw_url = "https://example.sharepoint.com/file?tempauth=SUPERSECRET"
        err = GraphError("request failed", url=raw_url)
        assert err.safe_url is not None
        assert "SUPERSECRET" not in err.safe_url

    def test_download_error_carries_status_code(self) -> None:
        err = DownloadError("bad", url="https://example.com/f?sig=X", status_code=403)
        assert err.status_code == 403
        assert "X" not in (err.safe_hint or "")

    def test_auth_error_carries_account_and_operation(self) -> None:
        err = AuthError("no token", account="alice", operation="acquire_silent")
        assert err.account == "alice"
        assert err.operation == "acquire_silent"
        assert err.code == "auth_error"

    def test_as_log_dict_contains_expected_keys(self) -> None:
        err = GraphError(
            "failed",
            url="https://graph.microsoft.com/v1.0/me/drive/root:/delta",
            account="bob",
            status_code=503,
        )
        d = err.as_log_dict()
        assert set(d.keys()) >= {"error_code", "account", "operation", "status_code", "hint"}
        assert d["account"] == "bob"
        assert d["status_code"] == 503
        # hint must not contain raw URL query params
        hint_str = str(d.get("hint", ""))
        assert "tempauth" not in hint_str

    def test_as_log_dict_no_sensitive_url_in_hint(self) -> None:
        raw_url = "https://example-my.sharepoint.com/personal/photo.jpg?tempauth=TOKEN99"
        err = DownloadError("download failed", url=raw_url)
        d = err.as_log_dict()
        assert "TOKEN99" not in str(d)

    def test_default_codes_assigned(self) -> None:
        assert GraphError("x").code == "graph_error"
        assert AuthError("x").code == "auth_error"
        assert DownloadError("x").code == "download_error"
        assert GhostItemError("x").code == "ghost_item"
        assert GraphThrottleError("x").code == "graph_throttle"
        assert GraphResyncRequired("x").code == "graph_resync_required"


# ---------------------------------------------------------------------------
# AuthError integration: verify auth module uses safe messages
# ---------------------------------------------------------------------------


class TestAuthModuleErrorMessages:
    """Validate that auth.py raises AuthError with safe messages."""

    def test_extract_token_raises_auth_error_with_safe_message(self) -> None:
        from nightfall_photo_ingress.adapters.onedrive.auth import OneDriveAuthClient

        client = OneDriveAuthClient()
        # Simulate MSAL returning error_description that could contain PII
        bad_result = {
            "error": "invalid_grant",
            "error_description": "AADSTS70008: user@contoso.com token expired",
        }
        with pytest.raises(AuthError) as exc_info:
            client._extract_token(bad_result, account="testacct")

        err = exc_info.value
        # Primary message must not expose the full MSAL error description with PII
        assert "user@contoso.com" not in str(err)
        # But it should be reachable as a hint for structured logging
        assert "user@contoso.com" in (err.safe_hint or "")
        assert err.account == "testacct"

    def test_extract_token_raises_on_none_result(self) -> None:
        from nightfall_photo_ingress.adapters.onedrive.auth import OneDriveAuthClient

        client = OneDriveAuthClient()
        with pytest.raises(AuthError):
            client._extract_token(None, account="testacct")

    def test_extract_token_raises_on_missing_access_token_key(self) -> None:
        from nightfall_photo_ingress.adapters.onedrive.auth import OneDriveAuthClient

        client = OneDriveAuthClient()
        with pytest.raises(AuthError):
            client._extract_token({"error": "no_token"}, account="testacct")
