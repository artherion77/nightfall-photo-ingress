"""Tests for Chunk 2: retry policy, Retry-After parsing, and back-off integration.

Coverage:
- classify_status: all retryable and non-retryable status codes.
- parse_retry_after: numeric seconds, HTTP-date, malformed, None, empty.
- compute_delay: server hint, exponential back-off, cap enforcement, jitter.
- download_with_retry: 429/5xx retry, transport error retry, exhaustion, URL redaction.
- _graph_get_json: 429/5xx retry, transport error retry, exhaustion.
"""

from __future__ import annotations

import json as json_mod
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from nightfall_photo_ingress.adapters.onedrive.client import (
    _graph_get_json,
    download_with_retry,
)
from nightfall_photo_ingress.adapters.onedrive.errors import DownloadError, GraphError
from nightfall_photo_ingress.adapters.onedrive.retry import (
    RETRYABLE_STATUS_CODES,
    RetryPolicy,
    classify_status,
    compute_delay,
    parse_retry_after,
)

# ---------------------------------------------------------------------------
# Deterministic zero-jitter helper for tests
# ---------------------------------------------------------------------------

_NO_JITTER: "Callable[[], float]" = lambda: 0.0  # noqa: E731


# ---------------------------------------------------------------------------
# Mock response factory
# ---------------------------------------------------------------------------


def _resp(
    status_code: int,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    text: str | None = None,
) -> MagicMock:
    """Create a minimal mock HTTP response that satisfies the adapter code."""
    r = MagicMock()
    r.status_code = status_code
    r.content = body
    r.text = text if text is not None else (body.decode() if body else "")
    r.headers = headers or {}
    r.iter_bytes.return_value = [body] if body else []
    return r


def _json_resp(payload: dict) -> MagicMock:
    """Create a 200 OK mock response whose body is serialised JSON."""
    text = json_mod.dumps(payload)
    return _resp(200, text.encode(), text=text)


def _mock_client(*responses) -> MagicMock:
    """Build a mock httpx.Client whose get() returns/raises responses in order."""
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = list(responses)
    return client


# ---------------------------------------------------------------------------
# classify_status
# ---------------------------------------------------------------------------


class TestClassifyStatus:
    def test_429_retryable(self):
        assert classify_status(429) is True

    def test_500_retryable(self):
        assert classify_status(500) is True

    def test_502_retryable(self):
        assert classify_status(502) is True

    def test_503_retryable(self):
        assert classify_status(503) is True

    def test_504_retryable(self):
        assert classify_status(504) is True

    def test_200_not_retryable(self):
        assert classify_status(200) is False

    def test_400_not_retryable(self):
        assert classify_status(400) is False

    def test_401_not_retryable(self):
        assert classify_status(401) is False

    def test_404_not_retryable(self):
        assert classify_status(404) is False

    def test_retryable_set_matches_constant(self):
        for code in RETRYABLE_STATUS_CODES:
            assert classify_status(code) is True


# ---------------------------------------------------------------------------
# parse_retry_after
# ---------------------------------------------------------------------------


class TestParseRetryAfter:
    def test_none_returns_none(self):
        assert parse_retry_after(None) is None

    def test_empty_string_returns_none(self):
        assert parse_retry_after("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_retry_after("   ") is None

    def test_numeric_integer_seconds(self):
        assert parse_retry_after("60") == 60.0

    def test_numeric_zero(self):
        assert parse_retry_after("0") == 0.0

    def test_negative_clamped_to_zero(self):
        assert parse_retry_after("-5") == 0.0

    def test_whitespace_stripped(self):
        assert parse_retry_after("  30  ") == 30.0

    def test_http_date_past_returns_zero(self):
        # A date well in the past should clamp to 0.0.
        assert parse_retry_after("Thu, 01 Jan 2015 00:00:00 GMT") == 0.0

    def test_http_date_future_returns_positive(self):
        # A date far in the future must yield a large positive number.
        result = parse_retry_after("Thu, 31 Dec 2099 00:00:00 GMT")
        assert result is not None
        assert result > 3600  # at minimum one hour away

    def test_malformed_string_returns_none(self):
        assert parse_retry_after("not-a-value") is None

    def test_garbage_returns_none(self):
        assert parse_retry_after("!!!") is None


# ---------------------------------------------------------------------------
# compute_delay
# ---------------------------------------------------------------------------

_POLICY = RetryPolicy(max_attempts=4, base_delay=2.0, max_delay=60.0)


class TestComputeDelay:
    def test_retry_after_used_when_present(self):
        assert compute_delay(1, 30.0, _POLICY, _NO_JITTER) == 30.0

    def test_retry_after_capped_at_max_delay(self):
        assert compute_delay(1, 200.0, _POLICY, _NO_JITTER) == 60.0

    def test_exponential_backoff_attempt_1(self):
        # base * 2^0 = 2.0 (no jitter)
        assert compute_delay(1, None, _POLICY, _NO_JITTER) == 2.0

    def test_exponential_backoff_attempt_2(self):
        # base * 2^1 = 4.0
        assert compute_delay(2, None, _POLICY, _NO_JITTER) == 4.0

    def test_exponential_backoff_attempt_3(self):
        # base * 2^2 = 8.0
        assert compute_delay(3, None, _POLICY, _NO_JITTER) == 8.0

    def test_backoff_capped_at_max_delay(self):
        # Large attempt → cap applies.
        assert compute_delay(10, None, _POLICY, _NO_JITTER) == 60.0

    def test_jitter_added_to_backoff(self):
        jitter_fn = lambda: 0.5  # noqa: E731
        # base * 2^0 + 0.5 = 2.5
        assert compute_delay(1, None, _POLICY, jitter_fn) == 2.5

    def test_jitter_still_capped(self):
        jitter_fn = lambda: 999.0  # noqa: E731
        assert compute_delay(1, None, _POLICY, jitter_fn) == 60.0


# ---------------------------------------------------------------------------
# download_with_retry
# ---------------------------------------------------------------------------

_DL_POLICY = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0)
_NOOP_SLEEP = MagicMock()


class TestDownloadWithRetry:
    def setup_method(self):
        _NOOP_SLEEP.reset_mock()

    def test_success_first_attempt(self, tmp_path: Path):
        client = _mock_client(_resp(200, b"photo"))
        dest = tmp_path / "f.jpg"
        sleeper = MagicMock()
        download_with_retry(
            client,
            "http://cdn.example.com/f",
            dest,
            expected_size=5,
            policy=_DL_POLICY,
            sleeper=sleeper,
            jitter_fn=_NO_JITTER,
        )
        assert dest.read_bytes() == b"photo"
        sleeper.assert_not_called()

    def test_429_with_retry_after_sleeps_and_succeeds(self, tmp_path: Path):
        client = _mock_client(
            _resp(429, headers={"Retry-After": "5"}),
            _resp(200, b"ok"),
        )
        sleeper = MagicMock()
        dest = tmp_path / "f.jpg"
        download_with_retry(
            client,
            "http://cdn.example.com/f",
            dest,
            expected_size=2,
            policy=_DL_POLICY,
            sleeper=sleeper,
            jitter_fn=_NO_JITTER,
        )
        sleeper.assert_called_once_with(5.0)
        assert dest.read_bytes() == b"ok"

    def test_429_without_retry_after_uses_exponential_backoff(self, tmp_path: Path):
        client = _mock_client(_resp(429), _resp(200, b"ok"))
        sleeper = MagicMock()
        dest = tmp_path / "f.jpg"
        download_with_retry(
            client,
            "http://cdn.example.com/f",
            dest,
            expected_size=2,
            policy=_DL_POLICY,
            sleeper=sleeper,
            jitter_fn=_NO_JITTER,
        )
        # attempt=1, base=1.0 → 1.0 * 2^0 = 1.0 (zero jitter)
        sleeper.assert_called_once_with(1.0)

    def test_500_retried(self, tmp_path: Path):
        client = _mock_client(_resp(500), _resp(200, b"ok"))
        sleeper = MagicMock()
        dest = tmp_path / "out"
        download_with_retry(
            client,
            "http://cdn.example.com/f",
            dest,
            expected_size=2,
            policy=_DL_POLICY,
            sleeper=sleeper,
            jitter_fn=_NO_JITTER,
        )
        assert sleeper.call_count == 1

    def test_502_retried(self, tmp_path: Path):
        client = _mock_client(_resp(502), _resp(200, b"ok"))
        dest = tmp_path / "out"
        download_with_retry(
            client,
            "http://cdn.example.com/f",
            dest,
            expected_size=2,
            policy=_DL_POLICY,
            sleeper=MagicMock(),
            jitter_fn=_NO_JITTER,
        )

    def test_504_retried(self, tmp_path: Path):
        client = _mock_client(_resp(504), _resp(200, b"ok"))
        dest = tmp_path / "out"
        download_with_retry(
            client,
            "http://cdn.example.com/f",
            dest,
            expected_size=2,
            policy=_DL_POLICY,
            sleeper=MagicMock(),
            jitter_fn=_NO_JITTER,
        )

    def test_retry_exhausted_raises_download_error(self, tmp_path: Path):
        client = _mock_client(_resp(429), _resp(429), _resp(429))
        sleeper = MagicMock()
        dest = tmp_path / "out"
        with pytest.raises(DownloadError) as exc_info:
            download_with_retry(
                client,
                "http://cdn.example.com/f",
                dest,
                expected_size=2,
                policy=_DL_POLICY,
                sleeper=sleeper,
                jitter_fn=_NO_JITTER,
            )
        assert exc_info.value.code == "download_retry_exhausted"
        # Sleeps after attempt 1 and 2; raises on attempt 3.
        assert sleeper.call_count == 2

    def test_transport_error_retried(self, tmp_path: Path):
        client = _mock_client(httpx.ConnectError("refused"), _resp(200, b"ok"))
        sleeper = MagicMock()
        dest = tmp_path / "out"
        download_with_retry(
            client,
            "http://cdn.example.com/f",
            dest,
            expected_size=2,
            policy=_DL_POLICY,
            sleeper=sleeper,
            jitter_fn=_NO_JITTER,
        )
        assert sleeper.call_count == 1
        assert dest.read_bytes() == b"ok"

    def test_transport_error_exhausted_raises(self, tmp_path: Path):
        client = _mock_client(
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
        )
        dest = tmp_path / "out"
        with pytest.raises(DownloadError) as exc_info:
            download_with_retry(
                client,
                "http://cdn.example.com/f",
                dest,
                expected_size=2,
                policy=_DL_POLICY,
                sleeper=MagicMock(),
                jitter_fn=_NO_JITTER,
            )
        assert exc_info.value.code == "download_transport_error"

    def test_non_retryable_4xx_raised_immediately(self, tmp_path: Path):
        client = _mock_client(_resp(404))
        sleeper = MagicMock()
        dest = tmp_path / "out"
        with pytest.raises(DownloadError):
            download_with_retry(
                client,
                "http://cdn.example.com/f",
                dest,
                expected_size=2,
                policy=_DL_POLICY,
                sleeper=sleeper,
                jitter_fn=_NO_JITTER,
            )
        sleeper.assert_not_called()

    def test_sensitive_url_not_in_exception(self, tmp_path: Path):
        """Pre-authenticated URL secrets must never appear in exception strings."""
        secret = "https://cdn.onedrive.com/f?tempauth=TOPSECRET&sig=ABCDEF"
        client = _mock_client(_resp(429), _resp(429), _resp(429))
        dest = tmp_path / "out"
        with pytest.raises(DownloadError) as exc_info:
            download_with_retry(
                client,
                secret,
                dest,
                expected_size=2,
                policy=_DL_POLICY,
                sleeper=MagicMock(),
                jitter_fn=_NO_JITTER,
            )
        assert "TOPSECRET" not in str(exc_info.value)
        assert "TOPSECRET" not in (exc_info.value.safe_hint or "")


# ---------------------------------------------------------------------------
# _graph_get_json
# ---------------------------------------------------------------------------

_GRAPH_POLICY = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0)
_GRAPH_URL = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"


class TestGraphGetJson:
    def test_success_returns_parsed_json(self):
        payload = {"value": [], "@odata.deltaLink": "https://graph.example.com/delta?token=x"}
        client = _mock_client(_json_resp(payload))
        result = _graph_get_json(client, _GRAPH_URL, "tok", _GRAPH_POLICY, MagicMock(), _NO_JITTER)
        assert result["@odata.deltaLink"] == payload["@odata.deltaLink"]

    def test_429_retried_with_retry_after(self):
        payload = {"value": []}
        client = _mock_client(_resp(429, headers={"Retry-After": "3"}), _json_resp(payload))
        sleeper = MagicMock()
        _graph_get_json(client, _GRAPH_URL, "tok", _GRAPH_POLICY, sleeper, _NO_JITTER)
        sleeper.assert_called_once_with(3.0)

    def test_503_retried(self):
        payload = {"value": []}
        client = _mock_client(_resp(503), _json_resp(payload))
        sleeper = MagicMock()
        _graph_get_json(client, _GRAPH_URL, "tok", _GRAPH_POLICY, sleeper, _NO_JITTER)
        assert sleeper.call_count == 1

    def test_retry_exhausted_raises_graph_error(self):
        client = _mock_client(_resp(503), _resp(503), _resp(503))
        with pytest.raises(GraphError) as exc_info:
            _graph_get_json(client, _GRAPH_URL, "tok", _GRAPH_POLICY, MagicMock(), _NO_JITTER)
        assert exc_info.value.code == "graph_retry_exhausted"

    def test_transport_error_retried(self):
        payload = {"value": []}
        client = _mock_client(httpx.ConnectError("refused"), _json_resp(payload))
        sleeper = MagicMock()
        _graph_get_json(client, _GRAPH_URL, "tok", _GRAPH_POLICY, sleeper, _NO_JITTER)
        assert sleeper.call_count == 1

    def test_transport_error_exhausted_raises_graph_error(self):
        client = _mock_client(
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
        )
        with pytest.raises(GraphError) as exc_info:
            _graph_get_json(client, _GRAPH_URL, "tok", _GRAPH_POLICY, MagicMock(), _NO_JITTER)
        assert exc_info.value.code == "graph_transport_error"
