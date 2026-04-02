"""Dedicated tests for V2-9 throughput and adaptive backpressure."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pytest

from nightfall_photo_ingress.config import AccountConfig, AppConfig, CoreConfig, LoggingConfig
from nightfall_photo_ingress.adapters.onedrive.retry import DEFAULT_POLICY
from nightfall_photo_ingress.adapters.onedrive.client import (
    _incident_state_path,
    _poll_single_account,
    _runtime_budget_exhausted_result,
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


def _make_app_config(
    tmp_path: Path,
    accounts: tuple[AccountConfig, ...],
    *,
    worker_count: int = 1,
    adaptive: bool = True,
    backpressure_retry_threshold: int = 1,
) -> AppConfig:
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
        account_worker_count=worker_count,
        adaptive_backpressure_enabled=adaptive,
        backpressure_retry_threshold=backpressure_retry_threshold,
        backpressure_transport_error_threshold=99,
        backpressure_cooldown_seconds=60,
    )
    return AppConfig(
        source_path=tmp_path / "photo-ingress.conf",
        core=core,
        logging=LoggingConfig(),
        accounts=accounts,
    )


def test_v2_chunk9_parallel_worker_mode_preserves_result_order(tmp_path: Path) -> None:
    """Parallel worker mode should still return results in config order."""

    first = _make_account(tmp_path, "zzz", "/CameraA")
    second = _make_account(tmp_path, "aaa", "/CameraB")
    app_config = _make_app_config(tmp_path, (first, second), worker_count=2)

    def factory() -> _FakeClient:
        return _FakeClient(
            {
                "https://graph.microsoft.com/v1.0/me/drive/root:/CameraA:/delta": [
                    _FakeResponse(status_code=200, text='{"value":[],"@odata.deltaLink":"https://delta/zzz"}')
                ],
                "https://graph.microsoft.com/v1.0/me/drive/root:/CameraB:/delta": [
                    _FakeResponse(status_code=200, text='{"value":[],"@odata.deltaLink":"https://delta/aaa"}')
                ],
            }
        )

    results = poll_accounts(
        app_config=app_config,
        auth_client=_FakeAuthClient(),
        http_client_factory=factory,
    )

    assert [res.account_name for res in results] == ["zzz", "aaa"]


def test_v2_chunk9_adaptive_backpressure_arms_cooldown(tmp_path: Path) -> None:
    """High retry anomalies should arm account cooldown when adaptive mode is enabled."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    app_config = _make_app_config(tmp_path, (account,), backpressure_retry_threshold=1)

    def factory() -> _FakeClient:
        return _FakeClient(
            {
                "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                    _FakeResponse(
                        status_code=200,
                        text=(
                            '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                            '"size":3,"@microsoft.graph.downloadUrl":"https://download/a1"}],'
                            '"@odata.deltaLink":"https://delta/final"}'
                        ),
                    )
                ],
                "https://download/a1": [
                    _FakeResponse(status_code=429, headers={"Retry-After": "0"}),
                    _FakeResponse(status_code=200, content=b"one"),
                ],
            }
        )

    poll_accounts(
        app_config=app_config,
        auth_client=_FakeAuthClient(),
        http_client_factory=factory,
        sleeper=lambda _seconds: None,
        jitter_fn=lambda: 0.0,
    )

    incident_state = json.loads(_incident_state_path(account.delta_cursor).read_text(encoding="utf-8"))
    assert incident_state.get("cooldown_until_epoch")


def test_v2_chunk9_runtime_budget_exhausted_result_shape() -> None:
    """Runtime budget fallback result should expose scheduler anomaly cleanly."""

    result = _runtime_budget_exhausted_result("alice")
    assert result.account_name == "alice"
    assert result.candidate_count == 0
    assert result.delta_anomaly_count == 1
    assert dict(result.delta_anomaly_reason_counts) == {
        "scheduler_runtime_budget_exhausted": 1
    }


def test_v2_chunk9_single_account_budget_exhaustion_short_circuits(tmp_path: Path) -> None:
    """Single account helper should return scheduler anomaly when deadline already passed."""

    account = _make_account(tmp_path, "alice", "/Camera Roll")
    app_config = _make_app_config(tmp_path, (account,))
    result = _poll_single_account(
        account=account,
        app_config=app_config,
        auth=_FakeAuthClient(),
        http_client_factory=lambda: _FakeClient({}),
        page_handoff_processor=None,
        poll_run_id="run-1",
        deadline=0.0,
        policy=DEFAULT_POLICY,
        sleeper=lambda _seconds: None,
        jitter_fn=lambda: 0.0,
    )

    assert result.candidate_count == 0
    assert dict(result.delta_anomaly_reason_counts) == {
        "scheduler_runtime_budget_exhausted": 1
    }
