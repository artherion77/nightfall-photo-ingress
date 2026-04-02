"""Unit tests for OneDrive authentication helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import stat

import pytest

from nightfall_photo_ingress.config import AccountConfig
from nightfall_photo_ingress.adapters.onedrive.auth import AuthError, OneDriveAuthClient


@dataclass
class _FakeCache:
    has_state_changed: bool = False
    _serialized: str = "{}"

    def deserialize(self, payload: str) -> None:
        self._serialized = payload

    def serialize(self) -> str:
        return self._serialized


class _FakeApp:
    def __init__(self, result: dict[str, object], accounts: list[dict[str, object]] | None = None):
        self._result = result
        self._accounts = accounts if accounts is not None else [{"home_account_id": "1"}]
        self.last_scopes: list[str] | None = None

    def initiate_device_flow(self, scopes: list[str]) -> dict[str, str]:
        self.last_scopes = list(scopes)
        return {
            "user_code": "AAAA-BBBB",
            "verification_uri": "https://microsoft.com/devicelogin",
        }

    def acquire_token_by_device_flow(self, flow: dict[str, str]) -> dict[str, object]:
        _ = flow
        return self._result

    def get_accounts(self) -> list[dict[str, object]]:
        return self._accounts

    def acquire_token_silently(
        self,
        scopes: list[str],
        account: dict[str, object],
    ) -> dict[str, object]:
        _ = scopes
        _ = account
        return self._result


@pytest.fixture
def account(tmp_path: Path) -> AccountConfig:
    return AccountConfig(
        name="alice",
        enabled=True,
        display_name="Alice",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="client-id",
        onedrive_root="/Camera Roll",
        token_cache=tmp_path / "alice" / "token_cache.json",
        delta_cursor=tmp_path / "alice" / "delta_cursor",
        max_downloads=20,
    )


def test_save_cache_enforces_0600_permissions(tmp_path: Path) -> None:
    """Cache file permissions should be corrected even when state is unchanged."""

    cache_path = tmp_path / "cache" / "token.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{}", encoding="utf-8")
    cache_path.chmod(0o644)

    client = OneDriveAuthClient()
    client._save_cache(cache_path, _FakeCache(has_state_changed=False))

    mode = stat.S_IMODE(cache_path.stat().st_mode)
    assert mode == 0o600


def test_auth_setup_returns_token_and_writes_cache(monkeypatch: pytest.MonkeyPatch, account: AccountConfig) -> None:
    """Device-code flow should return access token and persist secure cache file."""

    fake_cache = _FakeCache(has_state_changed=True, _serialized='{"token": true}')
    fake_app = _FakeApp(result={"access_token": "token-123"})

    monkeypatch.setattr(
        "nightfall_photo_ingress.adapters.onedrive.auth.msal.SerializableTokenCache",
        lambda: fake_cache,
    )
    monkeypatch.setattr(
        "nightfall_photo_ingress.adapters.onedrive.auth.msal.PublicClientApplication",
        lambda **kwargs: fake_app,
    )

    token = OneDriveAuthClient().auth_setup(account)
    assert token.token == "token-123"
    assert account.token_cache.exists()
    assert stat.S_IMODE(account.token_cache.stat().st_mode) == 0o600


def test_auth_setup_filters_reserved_scopes(
    monkeypatch: pytest.MonkeyPatch,
    account: AccountConfig,
) -> None:
    """Reserved OIDC scopes should never be passed to initiate_device_flow."""

    fake_cache = _FakeCache(has_state_changed=False)
    fake_app = _FakeApp(result={"access_token": "token-123"})

    monkeypatch.setattr(
        "nightfall_photo_ingress.adapters.onedrive.auth.msal.SerializableTokenCache",
        lambda: fake_cache,
    )
    monkeypatch.setattr(
        "nightfall_photo_ingress.adapters.onedrive.auth.msal.PublicClientApplication",
        lambda **kwargs: fake_app,
    )

    client = OneDriveAuthClient(scopes=["Files.Read", "offline_access", "openid", "profile"])
    client.auth_setup(account)

    assert fake_app.last_scopes == ["Files.Read"]


def test_acquire_access_token_requires_cached_account(
    monkeypatch: pytest.MonkeyPatch,
    account: AccountConfig,
) -> None:
    """Silent token acquisition should fail with actionable error when cache is empty."""

    fake_cache = _FakeCache(has_state_changed=False)
    fake_app = _FakeApp(result={"access_token": "unused"}, accounts=[])

    monkeypatch.setattr(
        "nightfall_photo_ingress.adapters.onedrive.auth.msal.SerializableTokenCache",
        lambda: fake_cache,
    )
    monkeypatch.setattr(
        "nightfall_photo_ingress.adapters.onedrive.auth.msal.PublicClientApplication",
        lambda **kwargs: fake_app,
    )

    with pytest.raises(AuthError, match="Run auth-setup first"):
        OneDriveAuthClient().acquire_access_token(account)


def test_load_expected_identity_migrates_legacy_sidecar(account: AccountConfig) -> None:
    client = OneDriveAuthClient()
    account.token_cache.parent.mkdir(parents=True, exist_ok=True)
    account.token_cache.parent.chmod(0o700)

    payload = {
        "home_account_id": "home-123",
        "username": "alice@example.com",
        "updated_at": "2026-04-02T00:00:00+00:00",
    }
    payload["integrity_sha256"] = client._identity_integrity_hash(payload, account)

    legacy_path = client._legacy_identity_path(account.token_cache)
    current_path = client._identity_path(account.token_cache)
    legacy_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    legacy_path.chmod(0o600)

    identity = client._load_expected_identity(account)

    assert identity == {"home_account_id": "home-123", "username": "alice@example.com"}
    assert current_path.exists()
    assert not legacy_path.exists()
