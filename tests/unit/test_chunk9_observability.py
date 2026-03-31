"""Tests for Chunk 9: observability and support diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightfall_photo_ingress.config import AccountConfig
from nightfall_photo_ingress.adapters.onedrive.client import _graph_get_json, poll_account_once


@dataclass
class _FakeResponse:
    status_code: int
    text: str = "{}"
    headers: dict[str, str] | None = None
    content: bytes = b""

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}

    def iter_bytes(self, chunk_size: int = 1024 * 1024):
        _ = chunk_size
        if self.content:
            yield self.content


class _CapturingClient:
    def __init__(self, mapping: dict[str, list[_FakeResponse]]) -> None:
        self._mapping = mapping
        self.request_headers: list[dict[str, str]] = []

    def get(self, url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        _ = args
        headers = kwargs.get("headers") or {}
        self.request_headers.append(dict(headers))
        queue = self._mapping.get(url)
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


def test_graph_requests_include_client_request_id_header() -> None:
    """Graph calls should include support correlation headers."""

    client = _CapturingClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive": [
                _FakeResponse(status_code=200, text='{"value":[]}')
            ]
        }
    )

    payload = _graph_get_json(
        http_client=client,
        url="https://graph.microsoft.com/v1.0/me/drive",
        access_token="token",
        diagnostics_counts={},
    )

    assert payload == {"value": []}
    assert client.request_headers
    first = client.request_headers[0]
    assert "client-request-id" in first
    assert first.get("return-client-request-id") == "true"
    assert first.get("Authorization") == "Bearer token"


def test_poll_account_once_counts_retry_and_throttle_diagnostics(tmp_path: Path) -> None:
    """Retry and throttle events should be exported via diagnostic counters."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _CapturingClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(status_code=429, headers={"Retry-After": "0"}),
                _FakeResponse(
                    status_code=200,
                    text='{"value":[],"@odata.deltaLink":"https://delta/final"}',
                ),
            ]
        }
    )

    _, _, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert ghost_counts == {}
    assert anomaly_counts.get("diag_retry_attempt_total", 0) >= 1
    assert anomaly_counts.get("diag_throttle_response_total", 0) >= 1


def test_graph_response_ids_are_counted_for_support_diagnostics(tmp_path: Path) -> None:
    """Graph request-id and correlation-id headers should be tracked."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _CapturingClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    headers={
                        "request-id": "req-123",
                        "x-ms-correlation-request-id": "corr-456",
                    },
                    text='{"value":[],"@odata.deltaLink":"https://delta/final"}',
                )
            ]
        }
    )

    _, _, _, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert anomaly_counts.get("diag_graph_response_request_id_seen_total") == 1
    assert anomaly_counts.get("diag_graph_response_correlation_id_seen_total") == 1
