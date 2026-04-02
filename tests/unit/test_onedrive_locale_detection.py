"""Tests for OneDrive account locale auto-detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightfall_photo_ingress.adapters.onedrive.client import detect_account_locale
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


def _make_account(tmp_path: Path) -> AccountConfig:
    return AccountConfig(
        name="alice",
        enabled=True,
        display_name="Alice",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="cid-alice",
        onedrive_root="/Camera Roll",
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
