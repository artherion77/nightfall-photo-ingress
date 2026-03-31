"""Tests for Chunk 4: download URL re-resolve and ghost-item classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightfall_photo_ingress.config import AccountConfig
from nightfall_photo_ingress.adapters.onedrive.client import poll_account_once


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


def test_download_url_reresolve_succeeds_after_first_403(tmp_path: Path) -> None:
    """A stale URL should be re-resolved once and then download successfully."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"size":3,"lastModifiedDateTime":"2026-01-01T00:00:00Z",'
                        '"@microsoft.graph.downloadUrl":"https://download/stale"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/stale": [_FakeResponse(status_code=403)],
            "https://graph.microsoft.com/v1.0/me/drive/items/a1": [
                _FakeResponse(
                    status_code=200,
                    text='{"id":"a1","@microsoft.graph.downloadUrl":"https://download/fresh"}',
                )
            ],
            "https://download/fresh": [_FakeResponse(status_code=200, content=b"one")],
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
    assert downloaded[0].read_bytes() == b"one"
    assert ghost_reason_counts == {}
    assert delta_anomaly_counts == {}


def test_missing_download_url_after_refresh_is_classified_as_ghost(tmp_path: Path) -> None:
    """If refresh payload has no download URL, the item should be ghost-classified."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"size":3,"lastModifiedDateTime":"2026-01-01T00:00:00Z",'
                        '"@microsoft.graph.downloadUrl":"https://download/stale"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/stale": [_FakeResponse(status_code=404)],
            "https://graph.microsoft.com/v1.0/me/drive/items/a1": [
                _FakeResponse(status_code=200, text='{"id":"a1"}')
            ],
        }
    )

    downloaded, candidate_count, ghost_reason_counts, delta_anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert candidate_count == 1
    assert downloaded == []
    assert ghost_reason_counts == {"ghost_missing_download_url_after_refresh": 1}
    assert delta_anomaly_counts == {}


def test_still_unreachable_after_refresh_is_classified_as_ghost(tmp_path: Path) -> None:
    """If refreshed URL still fails with 404/403/401, classify as ghost item."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"size":3,"lastModifiedDateTime":"2026-01-01T00:00:00Z",'
                        '"@microsoft.graph.downloadUrl":"https://download/stale"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/stale": [_FakeResponse(status_code=404)],
            "https://graph.microsoft.com/v1.0/me/drive/items/a1": [
                _FakeResponse(
                    status_code=200,
                    text='{"id":"a1","@microsoft.graph.downloadUrl":"https://download/fresh"}',
                )
            ],
            "https://download/fresh": [_FakeResponse(status_code=404)],
        }
    )

    downloaded, candidate_count, ghost_reason_counts, delta_anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert candidate_count == 1
    assert downloaded == []
    assert ghost_reason_counts == {"ghost_download_unreachable_after_refresh": 1}
    assert delta_anomaly_counts == {}


def test_refresh_404_classified_as_item_not_found_ghost(tmp_path: Path) -> None:
    """If metadata refresh endpoint returns 404, classify as not-found ghost."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"size":3,"lastModifiedDateTime":"2026-01-01T00:00:00Z",'
                        '"@microsoft.graph.downloadUrl":"https://download/stale"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/stale": [_FakeResponse(status_code=404)],
            "https://graph.microsoft.com/v1.0/me/drive/items/a1": [
                _FakeResponse(status_code=404)
            ],
        }
    )

    downloaded, candidate_count, ghost_reason_counts, delta_anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert candidate_count == 1
    assert downloaded == []
    assert ghost_reason_counts == {"ghost_item_not_found_on_refresh": 1}
    assert delta_anomaly_counts == {}
