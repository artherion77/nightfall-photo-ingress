"""Tests for Chunk 5: delta pagination hardening and resync marker flow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from nightfall_photo_ingress.config import AccountConfig
from nightfall_photo_ingress.adapters.onedrive.client import (
    GraphError,
    _resync_marker_path,
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


def test_repeated_nextlink_fails_with_explicit_cycle_error(tmp_path: Path) -> None:
    """Repeated nextLink values should terminate with a clear error."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[],"@odata.nextLink":"https://next/same"}',
                )
            ],
            "https://next/same": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[],"@odata.nextLink":"https://next/same"}',
                )
            ],
        }
    )

    with pytest.raises(GraphError, match="cycle detected") as exc_info:
        poll_account_once(
            account=account,
            staging_root=tmp_path / "staging",
            access_token="token",
            http_client=client,
        )

    assert exc_info.value.code == "delta_nextlink_cycle_detected"


def test_http_410_triggers_resync_marker_and_no_cursor_write(tmp_path: Path) -> None:
    """A 410 delta response should persist a resync marker and return safely."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=410,
                    headers={"Location": "https://graph.microsoft.com/v1.0/me/drive/root/delta?token=resync"},
                )
            ]
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert downloaded == []
    assert candidate_count == 0
    assert ghost_counts == {}
    assert anomaly_counts == {"delta_resync_required_410": 1}
    assert not account.delta_cursor.exists()

    marker_path = _resync_marker_path(account.delta_cursor)
    assert marker_path.exists()
    payload = json.loads(marker_path.read_text(encoding="utf-8"))
    assert payload["account"] == "alice"
    assert payload["reason"] == "delta_resync_required_410"
    assert payload["resync_url"] == "https://graph.microsoft.com/v1.0/me/drive/root/delta?token=resync"


def test_page_ceiling_enforced(tmp_path: Path) -> None:
    """Page ceiling should stop runaway pagination with a specific code."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[],"@odata.nextLink":"https://next/1"}',
                )
            ],
            "https://next/1": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[],"@odata.nextLink":"https://next/2"}',
                )
            ],
        }
    )

    with pytest.raises(GraphError, match="max pages") as exc_info:
        poll_account_once(
            account=account,
            staging_root=tmp_path / "staging",
            access_token="token",
            http_client=client,
            max_delta_pages=1,
        )

    assert exc_info.value.code == "delta_page_limit_exceeded"


def test_runtime_limit_enforced(tmp_path: Path) -> None:
    """Runtime ceiling should stop long polls with explicit error code."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[],"@odata.nextLink":"https://next/1"}',
                )
            ]
        }
    )

    with pytest.raises(GraphError, match="runtime limit") as exc_info:
        poll_account_once(
            account=account,
            staging_root=tmp_path / "staging",
            access_token="token",
            http_client=client,
            max_runtime_seconds=0,
        )

    assert exc_info.value.code == "delta_runtime_limit_exceeded"


def test_successful_poll_clears_existing_resync_marker(tmp_path: Path) -> None:
    """A successful poll should remove any stale resync marker file."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    marker = _resync_marker_path(account.delta_cursor)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"reason":"old"}', encoding="utf-8")

    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[],"@odata.deltaLink":"https://delta/final"}',
                )
            ]
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert downloaded == []
    assert candidate_count == 0
    assert ghost_counts == {}
    assert anomaly_counts == {}
    assert account.delta_cursor.read_text(encoding="utf-8") == "https://delta/final"
    assert not marker.exists()


def test_replayed_item_ids_are_counted_as_delta_anomaly(tmp_path: Path) -> None:
    """Repeated item IDs across pages should be surfaced and reduced deterministically."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"dup1","name":"IMG_1.HEIC","file":{},'
                        '"size":3,"@microsoft.graph.downloadUrl":"https://download/dup1"}],'
                        '"@odata.nextLink":"https://next/p2"}'
                    ),
                )
            ],
            "https://next/p2": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"dup1","name":"IMG_1_copy.HEIC","file":{},'
                        '"size":4,"@microsoft.graph.downloadUrl":"https://download/dup1b"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/dup1": [_FakeResponse(status_code=200, content=b"one")],
            "https://download/dup1b": [_FakeResponse(status_code=200, content=b"twoo")],
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert candidate_count == 1
    assert len(downloaded) == 1
    assert ghost_counts == {}
    assert anomaly_counts == {
        "delta_replayed_item_id": 1,
        "delta_reducer_event_overwrite": 1,
    }
