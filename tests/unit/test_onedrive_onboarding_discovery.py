"""Tests for OneDrive onboarding locale detection and path auto-discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightfall_photo_ingress.adapters.onedrive.client import (
    detect_account_locale,
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


def _make_account(tmp_path: Path, root: str = "/Camera Roll") -> AccountConfig:
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


def test_detect_account_locale_german(tmp_path: Path) -> None:
    account = _make_account(tmp_path)
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root/children?$select=name,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"Bilder","folder":{}},{"name":"Dokumente","folder":{}}]}',
                )
            ]
        }
    )

    locale = detect_account_locale(account=account, access_token="token", http_client=client)

    assert locale == "de"


def test_detect_account_locale_english(tmp_path: Path) -> None:
    account = _make_account(tmp_path)
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root/children?$select=name,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"Pictures","folder":{}},{"name":"Documents","folder":{}}]}',
                )
            ]
        }
    )

    locale = detect_account_locale(account=account, access_token="token", http_client=client)

    assert locale == "en"


def test_detect_account_locale_none_when_unrecognized(tmp_path: Path) -> None:
    account = _make_account(tmp_path)
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root/children?$select=name,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"Dokumente","folder":{}},{"name":"Desktop","folder":{}}]}',
                )
            ]
        }
    )

    locale = detect_account_locale(account=account, access_token="token", http_client=client)

    assert locale is None


def test_resolution_keeps_configured_path_when_valid(tmp_path: Path) -> None:
    account = _make_account(tmp_path, "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/special/cameraroll?$select=name,parentReference,specialFolder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
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


def test_resolution_promotes_special_camera_roll_over_valid_photos_folder(tmp_path: Path) -> None:
    account = _make_account(tmp_path, "/Bilder")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_1.JPG","file":{}},{"name":"IMG_2.JPG","file":{}}]}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/special/cameraroll?$select=name,parentReference,specialFolder": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"name":"Eigene Aufnahmen","parentReference":{"path":"/drive/root:/Bilder"},'
                        '"specialFolder":{"name":"cameraRoll"}}'
                    ),
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder/Eigene%20Aufnahmen:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_9.HEIC","file":{}}]}',
                )
            ],
        }
    )

    resolution = resolve_camera_roll_path_for_onboarding(
        account=account,
        access_token="token",
        http_client=client,
    )

    assert resolution.reason == "configured_path_not_camera_roll"
    assert resolution.suggested_path == "/Bilder/Eigene Aufnahmen"
    assert resolution.effective_path == "/Bilder/Eigene Aufnahmen"


def test_resolution_discovers_alternative_when_config_missing(tmp_path: Path) -> None:
    account = _make_account(tmp_path, "/Missing Path")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Missing%20Path:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/special/cameraroll?$select=name,parentReference,specialFolder": [
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
            "https://graph.microsoft.com/v1.0/me/drive/root:/Pictures?$select=name,parentReference,specialFolder": [
                _FakeResponse(
                    status_code=200,
                    text='{"name":"Pictures","parentReference":{"path":"/drive/root:"}}',
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


def test_resolution_prefers_special_cameraroll_alias(tmp_path: Path) -> None:
    account = _make_account(tmp_path, "/Missing Path")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Missing%20Path:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/special/cameraroll?$select=name,parentReference,specialFolder": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"name":"Eigene Aufnahmen","parentReference":{"path":"/drive/root:/Bilder"},'
                        '"specialFolder":{"name":"cameraRoll"}}'
                    ),
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder/Eigene%20Aufnahmen:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_1001.JPG","file":{}},{"name":"clip.mov","file":{}}]}',
                )
            ],
        }
    )

    resolution = resolve_camera_roll_path_for_onboarding(
        account=account,
        access_token="token",
        http_client=client,
    )

    assert resolution.reason == "configured_path_not_found"
    assert resolution.suggested_path == "/Bilder/Eigene Aufnahmen"
    assert resolution.suggested_media_count == 2
    assert resolution.effective_path == "/Bilder/Eigene Aufnahmen"


def test_resolution_prefers_camera_roll_special_folder_candidate_over_media_count(tmp_path: Path) -> None:
    account = _make_account(tmp_path, "/Camera Roll")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"readme.txt","file":{}}]}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/special/cameraroll?$select=name,parentReference,specialFolder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Pictures:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_1.JPG","file":{}},{"name":"IMG_2.JPG","file":{}},{"name":"IMG_3.JPG","file":{}}]}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Pictures?$select=name,parentReference,specialFolder": [
                _FakeResponse(
                    status_code=200,
                    text='{"name":"Pictures","parentReference":{"path":"/drive/root:"}}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Photos:/children?$select=name,file,folder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder/Eigene%20Aufnahmen:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_9.HEIC","file":{}}]}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder/Eigene%20Aufnahmen?$select=name,parentReference,specialFolder": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"name":"Eigene Aufnahmen","parentReference":{"path":"/drive/root:/Bilder"},'
                        '"specialFolder":{"name":"cameraRoll"}}'
                    ),
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_11.JPG","file":{}},{"name":"IMG_12.JPG","file":{}}]}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Bilder?$select=name,parentReference,specialFolder": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"name":"Bilder","parentReference":{"path":"/drive/root:"},'
                        '"specialFolder":{"name":"photos"}}'
                    ),
                )
            ],
        }
    )

    resolution = resolve_camera_roll_path_for_onboarding(
        account=account,
        access_token="token",
        http_client=client,
    )

    assert resolution.reason == "configured_path_has_no_media"
    assert resolution.suggested_path == "/Bilder/Eigene Aufnahmen"
    assert resolution.suggested_media_count == 1
    assert resolution.suggested_candidates[0].path == "/Pictures"
    assert resolution.suggested_candidates[1].path == "/Bilder"
    assert resolution.suggested_candidates[2].path == "/Bilder/Eigene Aufnahmen"


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
            "https://graph.microsoft.com/v1.0/me/drive/special/cameraroll?$select=name,parentReference,specialFolder": [
                _FakeResponse(status_code=404, text='{"error":{"code":"itemNotFound"}}')
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Pictures:/children?$select=name,file,folder": [
                _FakeResponse(
                    status_code=200,
                    text='{"value":[{"name":"IMG_9.HEIC","file":{}}]}',
                )
            ],
            "https://graph.microsoft.com/v1.0/me/drive/root:/Pictures?$select=name,parentReference,specialFolder": [
                _FakeResponse(
                    status_code=200,
                    text='{"name":"Pictures","parentReference":{"path":"/drive/root:"}}',
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
