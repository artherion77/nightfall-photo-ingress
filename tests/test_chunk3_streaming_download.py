"""Tests for Chunk 3: streamed download writes and integrity safeguards."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from nightfall_photo_ingress.onedrive.client import download_with_retry
from nightfall_photo_ingress.onedrive.errors import DownloadError
from nightfall_photo_ingress.onedrive.retry import RetryPolicy


class _StreamingResponse:
    """Minimal fake response supporting iter_bytes only."""

    def __init__(self, status_code: int, chunks: list[bytes], headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._chunks = chunks
        self.headers = headers or {}

    @property
    def content(self) -> bytes:
        raise AssertionError("download_with_retry must not access response.content")

    def iter_bytes(self, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        _ = chunk_size
        yield from self._chunks


def _client_with_responses(*responses: _StreamingResponse) -> MagicMock:
    client = MagicMock()
    client.get.side_effect = list(responses)
    return client


def test_streaming_download_writes_all_chunks(tmp_path: Path) -> None:
    """Chunked response bodies should be streamed to disk in order."""

    dest = tmp_path / "staging" / "asset.tmp"
    client = _client_with_responses(
        _StreamingResponse(200, [b"abc", b"def", b"ghi"]),
    )

    download_with_retry(
        http_client=client,
        url="https://download/asset",
        destination=dest,
        expected_size=9,
        policy=RetryPolicy(max_attempts=2, base_delay=0.01, max_delay=0.1),
        sleeper=lambda _: None,
        jitter_fn=lambda: 0.0,
    )

    assert dest.read_bytes() == b"abcdefghi"


def test_empty_200_body_with_expected_size_retries_then_fails(tmp_path: Path) -> None:
    """A 200 response with no body for non-empty file must be treated as anomaly."""

    dest = tmp_path / "staging" / "asset.tmp"
    client = _client_with_responses(
        _StreamingResponse(200, []),
        _StreamingResponse(200, []),
    )
    sleeps: list[float] = []

    with pytest.raises(DownloadError) as exc_info:
        download_with_retry(
            http_client=client,
            url="https://download/asset",
            destination=dest,
            expected_size=10,
            policy=RetryPolicy(max_attempts=2, base_delay=0.1, max_delay=2.0),
            sleeper=lambda s: sleeps.append(s),
            jitter_fn=lambda: 0.0,
        )

    assert exc_info.value.code == "download_empty_body"
    assert not dest.exists()
    assert sleeps == [0.1]


def test_size_mismatch_retries_and_succeeds(tmp_path: Path) -> None:
    """Byte-count mismatch should trigger retry and accept matching second response."""

    dest = tmp_path / "staging" / "asset.tmp"
    client = _client_with_responses(
        _StreamingResponse(200, [b"short"]),
        _StreamingResponse(200, [b"exact", b"size"]),
    )
    sleeps: list[float] = []

    download_with_retry(
        http_client=client,
        url="https://download/asset",
        destination=dest,
        expected_size=9,
        policy=RetryPolicy(max_attempts=2, base_delay=0.1, max_delay=2.0),
        sleeper=lambda s: sleeps.append(s),
        jitter_fn=lambda: 0.0,
    )

    assert dest.read_bytes() == b"exactsize"
    assert sleeps == [0.1]


def test_size_mismatch_final_attempt_fails_and_cleans_partial(tmp_path: Path) -> None:
    """Repeated mismatch should fail with explicit error and remove partial file."""

    dest = tmp_path / "staging" / "asset.tmp"
    client = _client_with_responses(
        _StreamingResponse(200, [b"x"]),
        _StreamingResponse(200, [b"y"]),
    )

    with pytest.raises(DownloadError) as exc_info:
        download_with_retry(
            http_client=client,
            url="https://download/asset",
            destination=dest,
            expected_size=10,
            policy=RetryPolicy(max_attempts=2, base_delay=0.1, max_delay=2.0),
            sleeper=lambda _: None,
            jitter_fn=lambda: 0.0,
        )

    assert exc_info.value.code == "download_size_mismatch"
    assert not dest.exists()


def test_zero_byte_expected_size_allowed(tmp_path: Path) -> None:
    """Expected zero-byte files should succeed with empty content."""

    dest = tmp_path / "staging" / "asset.tmp"
    client = _client_with_responses(_StreamingResponse(200, []))

    download_with_retry(
        http_client=client,
        url="https://download/asset",
        destination=dest,
        expected_size=0,
        policy=RetryPolicy(max_attempts=2, base_delay=0.1, max_delay=2.0),
        sleeper=lambda _: None,
        jitter_fn=lambda: 0.0,
    )

    assert dest.exists()
    assert dest.read_bytes() == b""
