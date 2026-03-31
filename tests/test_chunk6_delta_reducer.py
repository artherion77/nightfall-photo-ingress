"""Tests for Chunk 6: in-run delta dedupe/merge reducer behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightfall_photo_ingress.config import AccountConfig
from nightfall_photo_ingress.onedrive.client import poll_account_once


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


def test_duplicate_file_events_collapse_to_last_observed(tmp_path: Path) -> None:
    """Duplicate file events for one item ID should collapse to one final candidate."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"dup1","name":"IMG_1.HEIC","file":{},'
                        '"size":3,"@microsoft.graph.downloadUrl":"https://download/dup1-old"},'
                        '{"id":"dup1","name":"IMG_1.HEIC","file":{},'
                        '"size":4,"@microsoft.graph.downloadUrl":"https://download/dup1-new"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/dup1-new": [_FakeResponse(status_code=200, content=b"new!")],
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
    assert downloaded[0].name == "dup1.HEIC"
    assert downloaded[0].read_bytes() == b"new!"
    assert ghost_counts == {}
    assert anomaly_counts == {
        "delta_replayed_item_id": 1,
        "delta_reducer_event_overwrite": 1,
    }


def test_delete_then_create_for_same_item_id_keeps_final_create(tmp_path: Path) -> None:
    """Delete then create sequence should keep the final file candidate."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"item1","name":"IMG_OLD.HEIC","deleted":{}},'
                        '{"id":"item1","name":"IMG_NEW.HEIC","file":{},'
                        '"size":3,"@microsoft.graph.downloadUrl":"https://download/item1"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/item1": [_FakeResponse(status_code=200, content=b"new")],
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
    assert downloaded[0].read_bytes() == b"new"
    assert ghost_counts == {}
    assert anomaly_counts == {
        "delta_replayed_item_id": 1,
        "delta_reducer_event_overwrite": 1,
        "delta_reducer_tombstone_event": 1,
    }


def test_create_then_delete_for_same_item_id_emits_no_candidate(tmp_path: Path) -> None:
    """Create then delete should apply tombstone precedence and emit no candidate."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"item2","name":"IMG_2.HEIC","file":{},'
                        '"size":3,"@microsoft.graph.downloadUrl":"https://download/item2"},'
                        '{"id":"item2","name":"IMG_2.HEIC","deleted":{}}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert candidate_count == 0
    assert downloaded == []
    assert ghost_counts == {}
    assert anomaly_counts == {
        "delta_replayed_item_id": 1,
        "delta_reducer_event_overwrite": 1,
        "delta_reducer_tombstone_event": 1,
    }


def test_out_of_order_multi_item_events_produce_stable_final_state(tmp_path: Path) -> None:
    """Reducer should produce deterministic final candidates from out-of-order events."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a","name":"A1.HEIC","file":{},'
                        '"size":2,"@microsoft.graph.downloadUrl":"https://download/a1"},'
                        '{"id":"b","name":"B1.HEIC","file":{},'
                        '"size":2,"@microsoft.graph.downloadUrl":"https://download/b1"},'
                        '{"id":"a","name":"A2.HEIC","file":{},'
                        '"size":2,"@microsoft.graph.downloadUrl":"https://download/a2"},'
                        '{"id":"b","name":"B1.HEIC","deleted":{}},'
                        '{"id":"c","name":"C1.HEIC","file":{},'
                        '"size":2,"@microsoft.graph.downloadUrl":"https://download/c1"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/a2": [_FakeResponse(status_code=200, content=b"a2")],
            "https://download/c1": [_FakeResponse(status_code=200, content=b"c1")],
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert candidate_count == 2
    assert [p.name for p in downloaded] == ["a.HEIC", "c.HEIC"]
    assert [p.read_bytes() for p in downloaded] == [b"a2", b"c1"]
    assert ghost_counts == {}
    assert anomaly_counts == {
        "delta_replayed_item_id": 2,
        "delta_reducer_event_overwrite": 2,
        "delta_reducer_tombstone_event": 1,
    }
