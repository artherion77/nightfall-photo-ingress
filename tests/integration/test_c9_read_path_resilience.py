"""Chunk C9 validation tests for read-path retry/backoff resilience."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from nightfall_photo_ingress.adapters.onedrive.client import _graph_get_json, download_with_retry
from nightfall_photo_ingress.adapters.onedrive.errors import DownloadError, GraphError
from nightfall_photo_ingress.adapters.onedrive.retry import RetryPolicy


NO_JITTER = lambda: 0.0  # noqa: E731


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        text: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.text = text if text is not None else (body.decode("utf-8") if body else "")

    def iter_bytes(self, chunk_size: int = 1024 * 1024):
        del chunk_size
        if self._body:
            yield self._body


def make_graph_json_response(payload: dict[str, object], status_code: int = 200) -> FakeResponse:
    text = json.dumps(payload)
    return FakeResponse(status_code, body=text.encode("utf-8"), text=text)


def make_client(*responses_or_errors) -> MagicMock:
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = list(responses_or_errors)
    return client


def test_c9_graph_get_is_idempotent_for_repeated_get_requests() -> None:
    payload = {"value": [{"id": "1"}], "@odata.deltaLink": "next"}
    client = make_client(make_graph_json_response(payload), make_graph_json_response(payload))

    first = _graph_get_json(client, "https://graph.microsoft.com/v1.0/me/drive/root/delta", "token")
    second = _graph_get_json(client, "https://graph.microsoft.com/v1.0/me/drive/root/delta", "token")

    assert first == payload
    assert second == payload
    assert client.get.call_count == 2


def test_c9_graph_get_retries_on_5xx_then_succeeds() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0)
    sleeper = MagicMock()
    client = make_client(
        FakeResponse(503, text="temporarily unavailable"),
        make_graph_json_response({"value": []}),
    )

    payload = _graph_get_json(
        client,
        "https://graph.microsoft.com/v1.0/me/drive/root/delta",
        "token",
        policy=policy,
        sleeper=sleeper,
        jitter_fn=NO_JITTER,
    )

    assert payload == {"value": []}
    assert client.get.call_count == 2
    sleeper.assert_called_once_with(1.0)


def test_c9_graph_get_honors_retry_after_for_429() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0)
    sleeper = MagicMock()
    client = make_client(
        FakeResponse(429, headers={"Retry-After": "2"}, text="rate limited"),
        make_graph_json_response({"value": []}),
    )

    _graph_get_json(
        client,
        "https://graph.microsoft.com/v1.0/me/drive/root/delta",
        "token",
        policy=policy,
        sleeper=sleeper,
        jitter_fn=NO_JITTER,
    )

    sleeper.assert_called_once_with(2.0)
    assert client.get.call_count == 2


def test_c9_graph_get_does_not_retry_non_retryable_4xx() -> None:
    sleeper = MagicMock()
    client = make_client(FakeResponse(404, text="not found"))

    with pytest.raises(GraphError):
        _graph_get_json(
            client,
            "https://graph.microsoft.com/v1.0/me/drive/root/delta",
            "token",
            sleeper=sleeper,
            jitter_fn=NO_JITTER,
        )

    assert client.get.call_count == 1
    sleeper.assert_not_called()


def test_c9_graph_get_retries_network_error_then_succeeds() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0)
    sleeper = MagicMock()
    client = make_client(
        httpx.ConnectError("connection reset"),
        make_graph_json_response({"value": [{"id": "ok"}]}),
    )

    payload = _graph_get_json(
        client,
        "https://graph.microsoft.com/v1.0/me/drive/root/delta",
        "token",
        policy=policy,
        sleeper=sleeper,
        jitter_fn=NO_JITTER,
    )

    assert payload["value"] == [{"id": "ok"}]
    assert client.get.call_count == 2
    sleeper.assert_called_once_with(1.0)


def test_c9_graph_get_retry_is_bounded_and_exhausts() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0)
    sleeper = MagicMock()
    client = make_client(
        FakeResponse(503, text="transient"),
        FakeResponse(503, text="transient"),
        FakeResponse(503, text="transient"),
    )

    with pytest.raises(GraphError) as exc_info:
        _graph_get_json(
            client,
            "https://graph.microsoft.com/v1.0/me/drive/root/delta",
            "token",
            policy=policy,
            sleeper=sleeper,
            jitter_fn=NO_JITTER,
        )

    assert exc_info.value.code == "graph_retry_exhausted"
    assert client.get.call_count == 3
    assert sleeper.call_count == 2


def test_c9_download_read_retries_are_bounded_and_no_infinite_loop(tmp_path: Path) -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0)
    sleeper = MagicMock()
    client = make_client(
        httpx.ConnectError("down"),
        httpx.ConnectError("down"),
        httpx.ConnectError("down"),
    )

    with pytest.raises(DownloadError) as exc_info:
        download_with_retry(
            client,
            "https://download.example/file.jpg",
            tmp_path / "file.jpg",
            expected_size=10,
            policy=policy,
            sleeper=sleeper,
            jitter_fn=NO_JITTER,
        )

    assert exc_info.value.code == "download_transport_error"
    assert client.get.call_count == 3
    assert sleeper.call_count == 2
