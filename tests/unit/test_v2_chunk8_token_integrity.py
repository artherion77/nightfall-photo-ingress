"""Dedicated tests for V2-8 token lifecycle integrity hardening."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path

import pytest

from nightfall_photo_ingress.config import AccountConfig, AppConfig, CoreConfig, LoggingConfig
from nightfall_photo_ingress.adapters.onedrive.auth import AuthError, OneDriveAuthClient
from nightfall_photo_ingress.adapters.onedrive.cache_lock import SingletonLockBusyError
from nightfall_photo_ingress.adapters.onedrive.client import GraphError, poll_accounts


class _FakeMsalApp:
    def __init__(self, accounts: list[dict[str, object]]) -> None:
        self._accounts = accounts

    def get_accounts(self):
        return self._accounts

    def acquire_token_silently(self, scopes, account):
        _ = scopes
        _ = account
        return {"access_token": "token"}


class _FakeCache:
    has_state_changed = False


class _FakeAuthClient:
    def acquire_access_token(self, account: AccountConfig):
        return type("Token", (), {"token": f"token-for-{account.name}"})


def _make_account(tmp_path: Path, name: str = "alice") -> AccountConfig:
    account_dir = tmp_path / name
    account_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(account_dir, 0o700)
    return AccountConfig(
        name=name,
        enabled=True,
        display_name=name,
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id=f"cid-{name}",
        onedrive_root="/Camera Roll",
        token_cache=account_dir / "token.json",
        delta_cursor=account_dir / "cursor.txt",
        max_downloads=10,
    )


def _make_app_config(tmp_path: Path, account: AccountConfig) -> AppConfig:
    core = CoreConfig(
        config_version=2,
        poll_interval_minutes=15,
        process_accounts_in_config_order=True,
        staging_path=tmp_path / "staging",
        pending_path=tmp_path / "pending",
        accepted_path=tmp_path / "accepted",
        accepted_storage_template="{yyyy}/{mm}/{original}",
        rejected_path=tmp_path / "rejected",
        trash_path=tmp_path / "trash",
        registry_path=tmp_path / "registry.db",
        staging_on_same_pool=False,
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        verify_sha256_on_first_download=True,
        max_downloads_per_poll=10,
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


def test_v2_chunk8_tampered_identity_sidecar_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Acquire token should fail when identity sidecar integrity hash is tampered."""

    account = _make_account(tmp_path)
    account.token_cache.write_text("{}", encoding="utf-8")
    os.chmod(account.token_cache, 0o600)

    identity_path = account.token_cache.with_suffix(".json.identity.json")
    payload = {
        "home_account_id": "home-1",
        "username": "user@example.com",
        "integrity_sha256": "bad-hash",
    }
    identity_path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(identity_path, 0o600)

    auth = OneDriveAuthClient()

    monkeypatch.setattr(
        auth,
        "_build_app",
        lambda acct: (_FakeMsalApp([{"home_account_id": "home-1", "username": "user@example.com"}]), _FakeCache()),
    )

    with pytest.raises(AuthError, match="integrity mismatch"):
        auth.acquire_access_token(account)


def test_v2_chunk8_insecure_token_cache_permissions_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Acquire token should fail closed when cache permissions are too broad."""

    account = _make_account(tmp_path)
    account.token_cache.write_text("{}", encoding="utf-8")
    os.chmod(account.token_cache, 0o644)

    auth = OneDriveAuthClient()

    # Build app should fail before this is used, but keep patched app for isolation.
    monkeypatch.setattr(
        auth,
        "_build_app",
        lambda acct: (_FakeMsalApp([{"home_account_id": "home-1"}]), _FakeCache()),
    )

    with pytest.raises(AuthError, match="Insecure permissions"):
        auth._validate_secure_file(account.token_cache, 0o600)


def test_v2_chunk8_singleton_guard_blocks_concurrent_poll(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Poll should fail with explicit code when singleton lock is already held."""

    account = _make_account(tmp_path)
    app_config = _make_app_config(tmp_path, account)

    @contextmanager
    def _busy_lock(cache_path: Path):
        _ = cache_path
        raise SingletonLockBusyError("busy")
        yield

    monkeypatch.setattr("nightfall_photo_ingress.adapters.onedrive.client.account_singleton_lock", _busy_lock)

    with pytest.raises(GraphError, match="already being polled") as exc_info:
        poll_accounts(
            app_config,
            auth_client=_FakeAuthClient(),
            http_client_factory=lambda: None,
        )

    assert exc_info.value.code == "account_singleton_lock_busy"
