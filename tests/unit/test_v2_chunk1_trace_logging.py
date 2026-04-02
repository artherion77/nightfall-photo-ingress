"""Dedicated tests for Hardening Plan V2 Chunk 1 trace logging contract."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from nightfall_photo_ingress.config import AccountConfig
from nightfall_photo_ingress.logging_bootstrap import JsonFormatter
from nightfall_photo_ingress.adapters.onedrive.client import (
    _graph_get_json,
    download_with_retry,
    poll_account_once,
)
from nightfall_photo_ingress.adapters.onedrive.retry import RetryPolicy


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        text: str = "{}",
        headers: dict[str, str] | None = None,
        content: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self._content = content

    def iter_bytes(self, chunk_size: int = 1024 * 1024):
        _ = chunk_size
        if self._content:
            yield self._content


class _QueueClient:
    def __init__(self, responses_by_url: dict[str, list[_FakeResponse]]) -> None:
        self._responses_by_url = responses_by_url

    def get(self, url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        _ = args
        _ = kwargs
        queue = self._responses_by_url.get(url)
        if not queue:
            raise AssertionError(f"Unexpected URL requested: {url}")
        return queue.pop(0)


def _make_account(tmp_path: Path, name: str, root: str) -> AccountConfig:
    return AccountConfig(
        name=name,
        enabled=True,
        display_name=name,
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id=f"cid-{name}",
        onedrive_root=root,
        token_cache=tmp_path / name / "token.json",
        delta_cursor=tmp_path / name / "cursor.txt",
        max_downloads=10,
    )


def _trace_records(caplog):
    return [
        record
        for record in caplog.records
        if record.name == "nightfall_photo_ingress.adapters.onedrive.client"
        and record.msg == "onedrive_trace"
    ]


def test_json_formatter_includes_trace_extra_fields() -> None:
    """JSON formatter should serialize trace extra fields for observability."""

    logger = logging.getLogger("chunk1.trace.formatter")
    record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="onedrive_trace",
        args=(),
        exc_info=None,
        extra={
            "event": "graph_request_attempt_start",
            "poll_run_id": "poll-1",
            "account_name": "alice",
            "operation": "graph_get",
            "attempt": 1,
            "url": "https://example/redacted",
        },
    )

    payload = JsonFormatter().format(record)

    assert '"event": "graph_request_attempt_start"' in payload
    assert '"poll_run_id": "poll-1"' in payload
    assert '"account_name": "alice"' in payload
    assert '"operation": "graph_get"' in payload


def test_graph_trace_logs_attempt_retry_and_success(caplog) -> None:
    """Graph call should emit structured start/retry/success trace events."""

    caplog.set_level(logging.INFO, logger="nightfall_photo_ingress.adapters.onedrive.client")
    graph_url = "https://graph.microsoft.com/v1.0/me/drive"
    client = _QueueClient(
        {
            graph_url: [
                _FakeResponse(status_code=429, headers={"Retry-After": "0"}),
                _FakeResponse(status_code=200, text='{"value": []}'),
            ]
        }
    )

    _graph_get_json(
        http_client=client,
        url=graph_url,
        access_token="token",
        policy=RetryPolicy(max_attempts=2, base_delay=0.0, max_delay=0.0),
        sleeper=lambda _: None,
        jitter_fn=lambda: 0.0,
        diagnostics_counts={},
        account_name="alice",
        poll_run_id="poll-1",
    )

    records = _trace_records(caplog)
    assert records

    events = [getattr(record, "event", "") for record in records]
    assert "graph_request_attempt_start" in events
    assert "graph_retry_scheduled" in events
    assert "graph_request_attempt_success" in events
    assert "graph_response_summary" in events

    for record in records:
        assert getattr(record, "poll_run_id", None) == "poll-1"
        assert getattr(record, "account_name", None) == "alice"
        assert getattr(record, "operation", None) in {"graph_get", None}


def test_download_trace_redacts_signed_query_values(caplog, tmp_path: Path) -> None:
    """Download trace events must not leak signed URL query strings."""

    caplog.set_level(logging.INFO, logger="nightfall_photo_ingress.adapters.onedrive.client")
    signed_url = "https://files.example/content?sig=secret-token&other=1"
    client = _QueueClient(
        {
            signed_url: [
                _FakeResponse(status_code=200, content=b"abc"),
            ]
        }
    )

    download_with_retry(
        http_client=client,
        url=signed_url,
        destination=tmp_path / "download.tmp",
        expected_size=3,
        account_name="alice",
        poll_run_id="poll-1",
        diagnostics_counts={},
    )

    records = _trace_records(caplog)
    assert records

    trace_urls = [str(getattr(record, "url", "")) for record in records]
    assert any(url == "https://files.example/content [query redacted]" for url in trace_urls)
    assert all("sig=" not in url for url in trace_urls)
    assert all("secret-token" not in url for url in trace_urls)
    assert "download_content_summary" in [getattr(record, "event", "") for record in records]


def test_delta_page_transitions_emit_trace_events(caplog, tmp_path: Path) -> None:
    """Account polling should emit delta page start/end trace events."""

    caplog.set_level(logging.INFO, logger="nightfall_photo_ingress.adapters.onedrive.client")
    account = _make_account(tmp_path, "alice", "/Camera Roll")
    delta_url = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"

    client = _QueueClient(
        {
            delta_url: [
                _FakeResponse(
                    status_code=200,
                    text='{"value": [], "@odata.deltaLink": "https://delta/final"}',
                )
            ]
        }
    )

    poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
        poll_run_id="poll-1",
        sleeper=MagicMock(),
    )

    records = _trace_records(caplog)
    events = [getattr(record, "event", "") for record in records]

    assert "delta_page_start" in events
    assert "delta_page_progress" in events
    assert "delta_cursor_checkpoint_saved" in events
    assert "delta_page_end" in events

    start = next(record for record in records if getattr(record, "event", "") == "delta_page_start")
    end = next(record for record in records if getattr(record, "event", "") == "delta_page_end")

    assert getattr(start, "poll_run_id", None) == "poll-1"
    assert getattr(start, "account_name", None) == "alice"
    assert getattr(end, "poll_run_id", None) == "poll-1"
    assert getattr(end, "account_name", None) == "alice"
