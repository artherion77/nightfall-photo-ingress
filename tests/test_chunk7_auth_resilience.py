"""Chunk 7 tests: auth cache resilience and refresh-once Graph auth flow."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pytest

from nightfall_photo_ingress.config import AccountConfig, AppConfig, CoreConfig, LoggingConfig
from nightfall_photo_ingress.onedrive.auth import AuthError, OneDriveAuthClient
from nightfall_photo_ingress.onedrive.client import poll_accounts


@dataclass
class _FakeCache:
    has_state_changed: bool = False

    def deserialize(self, payload: str) -> None:
        _ = payload

    def serialize(self) -> str:
        return "{}"


@dataclass
class _BrokenCache:
    has_state_changed: bool = False

    def deserialize(self, payload: str) -> None:
        _ = payload
        raise ValueError("corrupt payload")

    def serialize(self) -> str:
        return "{}"


class _FakeMsalApp:
    def __init__(self, result: dict[str, object], accounts: list[dict[str, object]]) -> None:
        self._result = result
        self._accounts = accounts

    def get_accounts(self) -> list[dict[str, object]]:
        return self._accounts

    def acquire_token_silently(self, scopes: list[str], account: dict[str, object]) -> dict[str, object]:
        _ = scopes
        _ = account
        return self._result

    def initiate_device_flow(self, scopes: list[str]) -> dict[str, str]:
        _ = scopes
        return {
            "user_code": "AAAA-BBBB",
            "verification_uri": "https://microsoft.com/devicelogin",
        }

    def acquire_token_by_device_flow(self, flow: dict[str, str]) -> dict[str, object]:
        _ = flow
        return self._result


class _HeaderAwareResponse:
    def __init__(self, status_code: int, text: str = "{}") -> None:
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {}

    def iter_bytes(self, chunk_size: int = 1024 * 1024):
        _ = chunk_size
        if False:
            yield b""


class _TokenAwareClient:
    def __init__(self, delta_url: str) -> None:
        self._delta_url = delta_url
        self.calls = 0

    def get(self, url: str, *args: Any, **kwargs: Any) -> _HeaderAwareResponse:
        _ = args
        headers = kwargs.get("headers") or {}
        self.calls += 1
        if url != self._delta_url:
            raise AssertionError(f"Unexpected URL: {url}")
        auth_header = headers.get("Authorization", "")
        if auth_header == "Bearer stale-token":
            return _HeaderAwareResponse(status_code=401, text="{}")
        if auth_header == "Bearer fresh-token":
            return _HeaderAwareResponse(
                status_code=200,
                text='{"value":[],"@odata.deltaLink":"https://delta/final"}',
            )
        return _HeaderAwareResponse(status_code=403, text="{}")

    def __enter__(self) -> "_TokenAwareClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type
        _ = exc
        _ = tb


class _RefreshingAuthClient:
    def __init__(self) -> None:
        self.calls = 0

    def acquire_access_token(self, account: AccountConfig):
        _ = account
        self.calls += 1
        token_value = "stale-token" if self.calls == 1 else "fresh-token"
        return type("Token", (), {"token": token_value})


def _make_account(tmp_path: Path) -> AccountConfig:
    return AccountConfig(
        name="alice",
        enabled=True,
        display_name="Alice",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="client-id",
        onedrive_root="/Camera Roll",
        token_cache=tmp_path / "alice" / "token_cache.json",
        delta_cursor=tmp_path / "alice" / "delta_cursor.txt",
        max_downloads=10,
    )


def _make_app_config(tmp_path: Path, account: AccountConfig) -> AppConfig:
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
        accounts=(account,),
    )


def test_corrupted_cache_is_quarantined(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Corrupted cache must be quarantined with an actionable error."""

    account = _make_account(tmp_path)
    account.token_cache.parent.mkdir(parents=True, exist_ok=True)
    account.token_cache.write_text("not-json", encoding="utf-8")

    monkeypatch.setattr(
        "nightfall_photo_ingress.onedrive.auth.msal.SerializableTokenCache",
        lambda: _BrokenCache(),
    )

    with pytest.raises(AuthError, match="Token cache is corrupted"):
        OneDriveAuthClient().acquire_access_token(account)

    quarantined = list(account.token_cache.parent.glob("token_cache.json.corrupt.*"))
    assert len(quarantined) == 1
    assert not account.token_cache.exists()


def test_wrong_bound_identity_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Silent auth must fail when cached account does not match persisted identity."""

    account = _make_account(tmp_path)
    account.token_cache.parent.mkdir(parents=True, exist_ok=True)
    account.token_cache.write_text("{}", encoding="utf-8")

    identity_path = account.token_cache.with_suffix(account.token_cache.suffix + ".identity.json")
    identity_path.write_text(
        json.dumps({"home_account_id": "expected", "username": "owner@example.com"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "nightfall_photo_ingress.onedrive.auth.msal.SerializableTokenCache",
        lambda: _FakeCache(),
    )
    monkeypatch.setattr(
        "nightfall_photo_ingress.onedrive.auth.msal.PublicClientApplication",
        lambda **kwargs: _FakeMsalApp(
            result={"access_token": "unused"},
            accounts=[{"home_account_id": "other", "username": "intruder@example.com"}],
        ),
    )

    with pytest.raises(AuthError, match="identity mismatch"):
        OneDriveAuthClient().acquire_access_token(account)


def test_graph_401_triggers_single_token_refresh(tmp_path: Path) -> None:
    """Graph 401 should trigger one forced refresh and then succeed."""

    account = _make_account(tmp_path)
    app_config = _make_app_config(tmp_path, account)
    auth_client = _RefreshingAuthClient()

    delta_url = "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta"

    def factory() -> _TokenAwareClient:
        return _TokenAwareClient(delta_url=delta_url)

    results = poll_accounts(
        app_config=app_config,
        auth_client=auth_client,
        http_client_factory=factory,
    )

    assert len(results) == 1
    assert results[0].candidate_count == 0
    assert auth_client.calls == 2
    assert account.delta_cursor.read_text(encoding="utf-8") == "https://delta/final"
