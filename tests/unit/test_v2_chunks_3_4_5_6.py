"""Dedicated tests for hardening V2 chunks 3, 4, 5, and 6.

Chunk coverage:
- V2-3: staging crash-recovery sweep
- V2-4: append-only lifecycle journal
- V2-5: integrity policy for uncertain download sizes
- V2-6: schema drift thresholds with fail-fast handling
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

import pytest

from nightfall_photo_ingress.config import AccountConfig, AppConfig, CoreConfig, LoggingConfig
from nightfall_photo_ingress.adapters.onedrive.client import GraphError, poll_account_once, poll_accounts


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


def _make_account(tmp_path: Path, name: str, root: str = "/Camera Roll") -> AccountConfig:
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
    drift_warning_threshold_ratio: float = 0.05,
    drift_critical_threshold_ratio: float = 0.2,
    drift_min_events_for_evaluation: int = 20,
    drift_fail_fast_enabled: bool = True,
) -> AppConfig:
    core = CoreConfig(
        config_version=1,
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
        max_downloads_per_poll=200,
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
        integrity_mode="strict",
        drift_warning_threshold_ratio=drift_warning_threshold_ratio,
        drift_critical_threshold_ratio=drift_critical_threshold_ratio,
        drift_min_events_for_evaluation=drift_min_events_for_evaluation,
        drift_fail_fast_enabled=drift_fail_fast_enabled,
    )
    return AppConfig(
        source_path=tmp_path / "photo-ingress.conf",
        core=core,
        logging=LoggingConfig(),
        accounts=accounts,
    )


def test_v2_chunk3_recovery_quarantines_stale_tmp_only(tmp_path: Path) -> None:
    """Startup recovery should quarantine stale .tmp without touching finalized files."""

    account = _make_account(tmp_path, "alice")
    staging_dir = tmp_path / "staging" / "alice"
    staging_dir.mkdir(parents=True, exist_ok=True)
    stale_tmp = staging_dir / "old.tmp"
    stale_tmp.write_bytes(b"partial")
    final_file = staging_dir / "safe.heic"
    final_file.write_bytes(b"ok")

    old_epoch = 946684800  # 2000-01-01 UTC
    os.utime(stale_tmp, (old_epoch, old_epoch))

    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(status_code=200, text='{"value":[],"@odata.deltaLink":"https://delta/final"}')
            ]
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
        tmp_ttl_minutes=1,
    )

    assert downloaded == []
    assert candidate_count == 0
    assert ghost_counts == {}
    assert anomaly_counts == {}
    assert final_file.exists()
    quarantine_dir = staging_dir / "_recovery_quarantine"
    assert quarantine_dir.exists()
    assert len(list(quarantine_dir.glob("old.tmp.*"))) == 1


def test_v2_chunk4_lifecycle_journal_has_ordered_events(tmp_path: Path) -> None:
    """A successful download should append started/completed/ready_for_hash events."""

    account = _make_account(tmp_path, "alice")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"size":3,"lastModifiedDateTime":"2026-01-01T00:00:00Z",'
                        '"@microsoft.graph.downloadUrl":"https://download/a1"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/a1": [_FakeResponse(status_code=200, content=b"one")],
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
    )

    assert len(downloaded) == 1
    assert candidate_count == 1
    assert ghost_counts == {}
    assert anomaly_counts == {}

    journal = tmp_path / "staging" / "alice" / "_lifecycle.journal.jsonl"
    lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert [entry["event"] for entry in lines] == [
        "download_started",
        "download_completed",
        "ready_for_hash",
    ]


def test_v2_chunk5_integrity_strict_blocks_uncertain_missing_size(tmp_path: Path) -> None:
    """Strict integrity mode must not silently accept downloads without expected size."""

    account = _make_account(tmp_path, "alice")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"@microsoft.graph.downloadUrl":"https://download/a1"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/a1": [_FakeResponse(status_code=200, content=b"one")],
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
        integrity_mode="strict",
    )

    assert downloaded == []
    assert candidate_count == 1
    assert ghost_counts == {"integrity_missing_expected_size_blocked": 1}
    assert anomaly_counts == {}


def test_v2_chunk5_integrity_tolerant_quarantines_uncertain_download(tmp_path: Path) -> None:
    """Tolerant integrity mode should quarantine uncertain downloads instead of accepting."""

    account = _make_account(tmp_path, "alice")
    client = _FakeClient(
        {
            "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                _FakeResponse(
                    status_code=200,
                    text=(
                        '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{},'
                        '"@microsoft.graph.downloadUrl":"https://download/a1"}],'
                        '"@odata.deltaLink":"https://delta/final"}'
                    ),
                )
            ],
            "https://download/a1": [_FakeResponse(status_code=200, content=b"one")],
        }
    )

    downloaded, candidate_count, ghost_counts, anomaly_counts = poll_account_once(
        account=account,
        staging_root=tmp_path / "staging",
        access_token="token",
        http_client=client,
        integrity_mode="tolerant",
    )

    assert downloaded == []
    assert candidate_count == 1
    assert ghost_counts == {"integrity_missing_expected_size_quarantined": 1}
    quarantine_file = tmp_path / "staging" / "alice" / "_quarantine" / "a1.heic"
    assert quarantine_file.exists()
    assert anomaly_counts == {}


def test_v2_chunk6_drift_critical_fail_fast(tmp_path: Path) -> None:
    """Critical schema drift should fail fast with explicit error code."""

    account = _make_account(tmp_path, "alice")
    app_config = _make_app_config(
        tmp_path,
        (account,),
        drift_warning_threshold_ratio=0.1,
        drift_critical_threshold_ratio=0.2,
        drift_min_events_for_evaluation=1,
        drift_fail_fast_enabled=True,
    )

    def factory() -> _FakeClient:
        return _FakeClient(
            {
                "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                    _FakeResponse(
                        status_code=200,
                        text=(
                            '{"value":['
                            '{"id":"a1","name":"IMG_1.HEIC","file":{}},'
                            '{"id":"a2","name":"IMG_2.HEIC","file":{}},'
                            '{"id":"a3","name":"IMG_3.HEIC","file":{}}],'
                            '"@odata.deltaLink":"https://delta/final"}'
                        ),
                    )
                ]
            }
        )

    with pytest.raises(GraphError, match="Schema drift threshold exceeded") as exc_info:
        poll_accounts(
            app_config,
            auth_client=_FakeAuthClient(),
            http_client_factory=factory,
        )

    assert exc_info.value.code == "drift_threshold_critical"


def test_v2_chunk6_drift_warning_does_not_fail_when_failfast_disabled(tmp_path: Path) -> None:
    """Warning drift state should not fail when fail-fast is disabled."""

    account = _make_account(tmp_path, "alice")
    app_config = _make_app_config(
        tmp_path,
        (account,),
        drift_warning_threshold_ratio=0.1,
        drift_critical_threshold_ratio=0.9,
        drift_min_events_for_evaluation=1,
        drift_fail_fast_enabled=False,
    )

    def factory() -> _FakeClient:
        return _FakeClient(
            {
                "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                    _FakeResponse(
                        status_code=200,
                        text=(
                            '{"value":[{"id":"a1","name":"IMG_1.HEIC","file":{}}],'
                            '"@odata.deltaLink":"https://delta/final"}'
                        ),
                    )
                ]
            }
        )

    results = poll_accounts(
        app_config,
        auth_client=_FakeAuthClient(),
        http_client_factory=factory,
    )

    assert len(results) == 1
    assert results[0].account_name == "alice"
    assert results[0].candidate_count == 1
    assert results[0].delta_anomaly_count >= 1
