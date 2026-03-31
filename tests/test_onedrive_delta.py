"""Unit and integration tests for OneDrive Graph polling and download logic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from nightfall_photo_ingress.config import AccountConfig, AppConfig, CoreConfig, LoggingConfig
from nightfall_photo_ingress.onedrive.client import (
    GraphError,
    download_with_retry,
    parse_delta_items,
    poll_account_once,
    poll_accounts,
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

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type
        _ = exc
        _ = tb


class _FakeAuthClient:
    def acquire_access_token(self, account: AccountConfig):
        return type("Token", (), {"token": f"token-for-{account.name}"})


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


def _make_app_config(tmp_path: Path, accounts: tuple[AccountConfig, ...]) -> AppConfig:
    core = CoreConfig(
        config_version=1,
        poll_interval_minutes=15,
        process_accounts_in_config_order=True,
        staging_path=tmp_path / "staging",
        accepted_path=tmp_path / "accepted",
        trash_path=tmp_path / "trash",
        registry_path=tmp_path / "registry.db",
        staging_on_same_pool=False,
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        verify_sha256_on_first_download=True,
        max_downloads_per_poll=100,
        max_poll_runtime_seconds=300,
        tmp_ttl_minutes=120,
        failed_ttl_hours=24,
        orphan_ttl_days=7,
        live_photo_capture_tolerance_seconds=3,
        live_photo_stem_mode="exact_stem",
        live_photo_component_order="photo_first",
        live_photo_conflict_policy="nearest_capture_time",
        sync_hash_import_enabled=True,
        sync_hash_import_path=tmp_path / "pictures",
        sync_hash_import_glob=".hashes.sha1",
    )
    return AppConfig(
        source_path=tmp_path / "photo-ingress.conf",
        core=core,
        logging=LoggingConfig(),
        accounts=accounts,
    )


def test_parse_delta_items_skips_deleted_non_files_and_missing_urls() -> None:
    """Only active file entries with download URLs should become candidates."""

    payload = {
        "value": [
            {"id": "1", "name": "deleted.heic", "deleted": {}},
            {"id": "2", "name": "folder", "folder": {}},
            {"id": "3", "name": "no-url.heic", "file": {}},
            {
                "id": "4",
                "name": "ok.heic",
                "file": {"mimeType": "image/heic"},
                "size": 123,
                "lastModifiedDateTime": "2026-01-01T00:00:00Z",
                "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                "@microsoft.graph.downloadUrl": "https://download/4",
            },
        ]
    }

    parsed = parse_delta_items("alice", payload)
    assert len(parsed) == 1
    assert parsed[0].item_id == "4"
    assert parsed[0].relative_path == "Camera Roll/2026"


def test_download_with_retry_honors_retry_after_header(tmp_path: Path) -> None:
    """Retryable responses should back off and then succeed."""

    sleeps: list[float] = []
    destination = tmp_path / "file.bin"
    client = _FakeClient(
        {
            "https://download/file": [
                _FakeResponse(status_code=429, headers={"Retry-After": "0"}),
                _FakeResponse(status_code=200, content=b"payload"),
            ]
        }
    )

    download_with_retry(
        http_client=client,
        url="https://download/file",
        destination=destination,
        expected_size=7,
        sleeper=lambda seconds: sleeps.append(seconds),
    )

    assert destination.read_bytes() == b"payload"
    assert sleeps == [0.0]


def test_poll_account_once_paginates_downloads_and_persists_cursor(tmp_path: Path) -> None:
    """Polling should follow nextLink pages and persist final delta cursor."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"size":3,"lastModifiedDateTime":"2026-01-01T00:00:00Z",'
                        '"@microsoft.graph.downloadUrl":"https://download/a1"}],'
                        '"@odata.nextLink":"https://next/page"}'
                    ),
                )
            ],
            "https://next/page": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a2","name":"IMG_2.MOV","file":{},'
                        '"size":3,"lastModifiedDateTime":"2026-01-01T00:00:01Z",'
                        '"@microsoft.graph.downloadUrl":"https://download/a2"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/a1": [_FakeResponse(status_code=200, content=b"one")],
            "https://download/a2": [_FakeResponse(status_code=200, content=b"two")],
        }
    )

    downloaded, candidate_count = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert candidate_count == 2
    assert len(downloaded) == 2
    assert account.delta_cursor.read_text(encoding="utf-8") == "https://delta/final"


def test_poll_accounts_runs_enabled_accounts_in_config_order(tmp_path: Path) -> None:
    """Enabled accounts must poll in declaration order from config."""

    first = _make_account(tmp_path, "zzz", "/CameraA")
    second = _make_account(tmp_path, "aaa", "/CameraB")
    app_config = _make_app_config(tmp_path, (first, second))

    call_order: list[str] = []

    def factory() -> _FakeClient:
        return _FakeClient(
            {
                "https://graph.microsoft.com/v1.0/me/drive/root:/CameraA:/delta": [
                    _FakeResponse(
                        status_code=200,
                        text='{"value":[],"@odata.deltaLink":"https://delta/zzz"}',
                    )
                ],
                "https://graph.microsoft.com/v1.0/me/drive/root:/CameraB:/delta": [
                    _FakeResponse(
                        status_code=200,
                        text='{"value":[],"@odata.deltaLink":"https://delta/aaa"}',
                    )
                ],
            }
        )

    original = poll_account_once

    def wrapped_poll_account_once(*args, **kwargs):
        call_order.append(kwargs["account"].name)
        return original(*args, **kwargs)

    monkey = pytest.MonkeyPatch()
    monkey.setattr("nightfall_photo_ingress.onedrive.client.poll_account_once", wrapped_poll_account_once)

    try:
        results = poll_accounts(
            app_config,
            auth_client=_FakeAuthClient(),
            http_client_factory=factory,
        )
    finally:
        monkey.undo()

    assert call_order == ["zzz", "aaa"]
    assert [res.account_name for res in results] == ["zzz", "aaa"]
    assert first.delta_cursor.read_text(encoding="utf-8") == "https://delta/zzz"
    assert second.delta_cursor.read_text(encoding="utf-8") == "https://delta/aaa"


def test_poll_account_once_errors_when_delta_link_missing(tmp_path: Path) -> None:
    """Missing deltaLink should fail with explicit error."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera Roll:/delta": [
                _FakeResponse(status_code=200, text='{"value":[]}')
            ]
        }
    )

    with pytest.raises(GraphError, match="No delta link returned"):
        poll_account_once(
            account=account,
            staging_root=tmp_path / "staging",
            access_token="token",
            http_client=client,
        )
