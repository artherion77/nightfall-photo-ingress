"""Dedicated tests for V2-7 delta anomaly breakers and escalation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from nightfall_photo_ingress.config import AccountConfig
from nightfall_photo_ingress.onedrive.client import (
    GraphError,
    _incident_state_path,
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


def _make_account(tmp_path: Path, name: str, root: str = "/Camera Roll") -> AccountConfig:
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


def test_v2_chunk7_escalates_to_forced_resync_after_loop_threshold(tmp_path: Path) -> None:
    """Repeated nextLink cycles should escalate to forced resync after threshold."""

    account = _make_account(tmp_path, "alice")
    initial = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"

    # First loop incident: still raises cycle error.
    client_first = _FakeClient(
        {
            initial: [_FakeResponse(status_code=200, text='{"value":[],"@odata.nextLink":"https://next/same"}')],
            "https://next/same": [_FakeResponse(status_code=200, text='{"value":[],"@odata.nextLink":"https://next/same"}')],
        }
    )
    with pytest.raises(GraphError, match="cycle detected"):
        poll_account_once(
            account=account,
            staging_root=tmp_path / "staging",
            access_token="token",
            http_client=client_first,
            delta_loop_resync_threshold=2,
        )

    # Second loop incident: should force resync instead of raising.
    client_second = _FakeClient(
        {
            initial: [_FakeResponse(status_code=200, text='{"value":[],"@odata.nextLink":"https://next/same"}')],
            "https://next/same": [_FakeResponse(status_code=200, text='{"value":[],"@odata.nextLink":"https://next/same"}')],
        }
    )
    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client_second,
        delta_loop_resync_threshold=2,
    )

    assert downloaded == []
    assert candidate_count == 0
    assert ghost_counts == {}
    assert anomaly_counts == {"delta_forced_resync_after_loop_threshold": 1}

    marker = _resync_marker_path(account.delta_cursor)
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["reason"] == "delta_forced_resync_after_loop_threshold"

    incident_state = json.loads(_incident_state_path(account.delta_cursor).read_text(encoding="utf-8"))
    assert incident_state.get("loop_incidents") == 0


def test_v2_chunk7_arms_ghost_breaker_and_applies_cooldown(tmp_path: Path) -> None:
    """Ghost anomaly threshold should arm cooldown and short-circuit next run."""

    account = _make_account(tmp_path, "alice")
    initial = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"

    # First run: missing expected size in strict mode -> ghost count increments.
    client_first = _FakeClient(
        {
            initial: [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"@microsoft.graph.downloadUrl":"https://download/a1"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/a1": [_FakeResponse(status_code=200, content=b"one")],
        }
    )
    _, _, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client_first,
        integrity_mode="strict",
        delta_breaker_ghost_threshold=1,
        delta_breaker_cooldown_seconds=300,
    )

    assert ghost_counts == {"integrity_missing_expected_size_blocked": 1}
    assert anomaly_counts.get("delta_breaker_armed_ghost") == 1

    # Second run should short-circuit immediately due to active cooldown.
    client_second = _FakeClient({})
    downloaded, candidate_count, ghost_counts_2, anomaly_counts_2 = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client_second,
    )

    assert downloaded == []
    assert candidate_count == 0
    assert ghost_counts_2 == {}
    assert anomaly_counts_2 == {"delta_breaker_cooldown_active": 1}


def test_v2_chunk7_arms_stale_breaker_on_replay_threshold(tmp_path: Path) -> None:
    """Replay anomalies should arm stale-page breaker when threshold is reached."""

    account = _make_account(tmp_path, "alice")
    initial = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"

    client = _FakeClient(
        {
            initial: [
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
            "https://download/dup1b": [_FakeResponse(status_code=200, content=b"twoo")],
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
        delta_breaker_stale_page_threshold=1,
        delta_breaker_cooldown_seconds=300,
    )

    assert len(downloaded) == 1
    assert candidate_count == 1
    assert ghost_counts == {}
    assert anomaly_counts.get("delta_replayed_item_id") == 1
    assert anomaly_counts.get("delta_breaker_armed_stale_page") == 1
