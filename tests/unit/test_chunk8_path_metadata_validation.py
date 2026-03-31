"""Chunk 8 tests: path safety and metadata validation tightening."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from nightfall_photo_ingress.config import AccountConfig
from nightfall_photo_ingress.adapters.onedrive.client import (
    _build_initial_delta_url,
    _extract_relative_path,
    download_candidates,
    poll_account_once,
)


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


class _FakeClient:
    def __init__(self, mapping: dict[str, list[_FakeResponse]]) -> None:
        self._mapping = mapping

    def get(self, url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        _ = args
        _ = kwargs
        queue = self._mapping.get(url)
        if not queue:
            raise AssertionError(f"Unexpected URL requested: {url}")
        return queue.pop(0)


def _make_account(tmp_path: Path, root: str = "/Camera Roll") -> AccountConfig:
    return AccountConfig(
        name="alice",
        enabled=True,
        display_name="Alice",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="cid-alice",
        onedrive_root=root,
        token_cache=tmp_path / "token.json",
        delta_cursor=tmp_path / "cursor.txt",
        max_downloads=10,
    )


def test_initial_delta_url_encodes_spaces_and_reserved_chars(tmp_path: Path) -> None:
    """Root path segments should be percent-encoded for Graph path addressing."""

    account = _make_account(tmp_path, root="/Camera Roll/2026 & Family")
    url = _build_initial_delta_url(account)

    assert url.endswith("/me/drive/root:/Camera%20Roll/2026%20%26%20Family:/delta")


def test_extract_relative_path_handles_missing_parent_reference() -> None:
    """Missing parentReference metadata must be treated as best-effort empty path."""

    assert _extract_relative_path({"id": "x1"}) == ""
    assert _extract_relative_path({"parentReference": "invalid"}) == ""


def test_poll_account_once_records_reason_codes_for_invalid_candidates(tmp_path: Path) -> None:
    """Malformed candidate payloads should be rejected with explicit anomaly codes."""

    account = _make_account(tmp_path)
    initial_url = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"
    client = _FakeClient(
        {
            initial_url: [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":['
                        '{"name":"no-id.heic","file":{},"@microsoft.graph.downloadUrl":"https://download/a"},'
                        '{"id":"m1","file":{},"@microsoft.graph.downloadUrl":"https://download/b"},'
                        '{"id":"m2","name":"bad-size.heic","file":{},"size":"NaN","@microsoft.graph.downloadUrl":"https://download/c"},'
                        '{"id":"ok1","name":"ok.heic","file":{},"size":3,"@microsoft.graph.downloadUrl":"https://download/ok"}'
                        '],"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/ok": [_FakeResponse(status_code=200, content=b"abc")],
        }
    )

    downloaded, candidate_count, ghost_reason_counts, delta_anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert candidate_count == 1
    assert len(downloaded) == 1
    assert ghost_reason_counts == {}
    assert delta_anomaly_counts["delta_item_missing_id"] == 1
    assert delta_anomaly_counts["delta_file_missing_name"] == 1
    assert delta_anomaly_counts["delta_file_invalid_size"] == 1


def test_download_candidates_sanitizes_staging_paths(tmp_path: Path) -> None:
    """Staging filenames should be sanitized from item IDs and extensions."""

    from nightfall_photo_ingress.adapters.onedrive.client import RemoteCandidate

    client = _FakeClient(
        {
            "https://download/1": [_FakeResponse(status_code=200, content=b"abc")],
        }
    )
    candidate = RemoteCandidate(
        account_name="alice",
        item_id="../weird/id:1",
        name="IMG_0001.HEIC",
        relative_path="",
        size_bytes=3,
        raw_modified_time="2026-01-01T00:00:00Z",
        normalized_modified_time="2026-01-01T00:00:00Z",
        download_url="https://download/1",
    )

    downloaded, reasons = download_candidates(
        candidates=[candidate],
        staging_root=tmp_path / "staging",
        account_name="alice",
        access_token="token",
        http_client=client,
    )

    assert reasons == {}
    assert len(downloaded) == 1
    assert downloaded[0].parent == tmp_path / "staging" / "alice"
    assert downloaded[0].name.endswith(".heic")
    assert ".." not in downloaded[0].name
    assert "/" not in downloaded[0].name
