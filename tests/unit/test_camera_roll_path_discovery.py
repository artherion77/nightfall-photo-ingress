"""Tests for camera-roll auto-discovery and path resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightfall_photo_ingress.adapters.onedrive.client import (
    resolve_camera_roll_path_for_onboarding,
)
from nightfall_photo_ingress.config import AccountConfig


@dataclass
class _FakeResponse:
    status_code: int
    text: str = "{}"
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}


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


def _make_account(tmp_path: Path, root: str) -> AccountConfig:
    return AccountConfig(
        name="alice",
        enabled=True,
        display_name="Alice",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="cid",
        onedrive_root=root,
        token_cache=tmp_path / "token.json",
        delta_cursor=tmp_path / "cursor.txt",
        max_downloads=10,
    )


def test_resolution_keeps_configured_path_when_valid(tmp_path: Path) -> None:
    account = _make_account(tmp_path, "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_1.HEIC","file":{}},{"name":"notes.txt","file":{}}]}',
                )
            ]
        }
    )

    resolution = resolve_camera_roll_path_for_onboarding(
        account=account,
        access_token="token",
        http_client=client,
    )

    assert resolution.reason is None
    assert resolution.suggested_path is None
    assert resolution.effective_path == "/Camera Roll"


def test_resolution_discovers_alternative_when_config_missing(tmp_path: Path) -> None:
    account = _make_account(tmp_path, "/Missing Path")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Missing%20Path:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Pictures:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_2.JPG","file":{}},{"name":"IMG_3.MOV","file":{}}]}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Photos:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder/Eigene%20Aufnahmen:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
        }
    )

    resolution = resolve_camera_roll_path_for_onboarding(
        account=account,
        access_token="token",
        http_client=client,
    )

    assert resolution.reason == "configured_path_not_found"
    assert resolution.suggested_path == "/Pictures"
    assert resolution.suggested_media_count == 2
    assert resolution.effective_path == "/Pictures"


def test_resolution_discovers_alternative_when_config_has_no_media(tmp_path: Path) -> None:
    account = _make_account(tmp_path, "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"readme.txt","file":{}},{"name":"archive.zip","file":{}}]}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Pictures:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_9.HEIC","file":{}}]}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Photos:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder/Eigene%20Aufnahmen:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
        }
    )

    resolution = resolve_camera_roll_path_for_onboarding(
        account=account,
        access_token="token",
        http_client=client,
    )

    assert resolution.reason == "configured_path_has_no_media"
    assert resolution.suggested_path == "/Pictures"
    assert resolution.effective_path == "/Pictures"
