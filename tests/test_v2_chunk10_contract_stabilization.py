"""Dedicated tests for V2-10 Module 4 interface contract stabilization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightfall_photo_ingress.config import AccountConfig, AppConfig, CoreConfig, LoggingConfig
from nightfall_photo_ingress.onedrive.client import (
    _split_anomaly_and_diagnostics,
    download_candidates,
    parse_delta_items,
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


def _make_account(tmp_path: Path) -> AccountConfig:
    return AccountConfig(
        name="alice",
        enabled=True,
        display_name="alice",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="cid-alice",
        onedrive_root="/Camera Roll",
        token_cache=tmp_path / "alice" / "token.json",
        delta_cursor=tmp_path / "alice" / "cursor.txt",
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


def test_v2_chunk10_result_sections_and_legacy_properties(tmp_path: Path) -> None:
    """Poll result should expose explicit sections and keep legacy aliases stable."""

    account = _make_account(tmp_path)
    app_config = _make_app_config(tmp_path, account)

    def factory() -> _FakeClient:
        return _FakeClient(
            {
                "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta": [
                    _FakeResponse(status_code=200, text='{"value":[],"@odata.deltaLink":"https://delta/final"}')
                ]
            }
        )

    result = poll_accounts(
        app_config=app_config,
        auth_client=_FakeAuthClient(),
        http_client_factory=factory,
    )[0]

    assert result.payload.candidate_count == 0
    assert result.anomalies.delta_anomaly_count == 0
    assert result.lifecycle_state.state == "normal"
    # Legacy properties remain available for downstream compatibility.
    assert result.candidate_count == 0
    assert result.delta_anomaly_count == 0


def test_v2_chunk10_timestamp_raw_and_normalized_fields() -> None:
    """Candidates should carry both raw and normalized timestamp fields."""

    payload = {
        "value": [
            {
                "id": "a1",
                "name": "IMG_1.HEIC",
                "file": {},
                "size": 1,
                "lastModifiedDateTime": "2026-01-01T00:00:00Z",
                "@microsoft.graph.downloadUrl": "https://download/a1",
            },
            {
                "id": "a2",
                "name": "IMG_2.HEIC",
                "file": {},
                "size": 1,
                "@microsoft.graph.downloadUrl": "https://download/a2",
            },
        ]
    }

    parsed = parse_delta_items("alice", payload)
    assert parsed[0].raw_modified_time == "2026-01-01T00:00:00Z"
    assert parsed[0].normalized_modified_time == "2026-01-01T00:00:00Z"
    assert parsed[1].raw_modified_time is None
    assert parsed[1].normalized_modified_time


def test_v2_chunk10_split_diagnostics_from_anomalies() -> None:
    """Mixed counter map should split into explicit anomalies and diagnostics sections."""

    anomalies, diagnostics = _split_anomaly_and_diagnostics(
        {
            "delta_file_missing_size": 2,
            "diag_retry_attempt_total": 3,
        }
    )
    assert anomalies == {"delta_file_missing_size": 2}
    assert diagnostics == {"retry_attempt_total": 3}


def test_v2_chunk10_collision_suffixing_is_deterministic(tmp_path: Path) -> None:
    """Sanitized basename collisions should produce deterministic hash suffixing."""

    candidates = parse_delta_items(
        "alice",
        {
            "value": [
                {
                    "id": "abc/def",
                    "name": "one.heic",
                    "file": {},
                    "size": 3,
                    "@microsoft.graph.downloadUrl": "https://download/1",
                },
                {
                    "id": "abc:def",
                    "name": "two.heic",
                    "file": {},
                    "size": 3,
                    "@microsoft.graph.downloadUrl": "https://download/2",
                },
            ]
        },
    )

    client = _FakeClient(
        {
            "https://download/1": [_FakeResponse(status_code=200, content=b"one")],
            "https://download/2": [_FakeResponse(status_code=200, content=b"two")],
        }
    )

    downloaded, ghost_counts = download_candidates(
        candidates=candidates,
        staging_root=tmp_path / "staging",
        account_name="alice",
        access_token="token",
        http_client=client,
    )

    assert ghost_counts == {}
    names = sorted(path.name for path in downloaded)
    assert any(name == "abc_def.heic" for name in names)
    assert any(name.startswith("abc_def-") and name.endswith(".heic") for name in names)
