"""Config validation tests for V2 hardening knobs (chunks 5 and 6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightfall_photo_ingress.config import ConfigError, load_config


def _write_config(tmp_path: Path, core_extra: str = "") -> Path:
    cfg = tmp_path / "photo-ingress.conf"
    cfg.write_text(
        (
            """
[core]
config_version = 2
poll_interval_minutes = 15
process_accounts_in_config_order = true
staging_path = /mnt/ssd/photo-ingress/staging
pending_path = /nightfall/media/photo-ingress/pending
accepted_path = /nightfall/media/photo-ingress/accepted
rejected_path = /nightfall/media/photo-ingress/rejected
trash_path = /nightfall/media/photo-ingress/trash
registry_path = /mnt/ssd/photo-ingress/registry.db
staging_on_same_pool = false
storage_template = {yyyy}/{mm}/{sha8}-{original}
verify_sha256_on_first_download = true
max_downloads_per_poll = 200
max_poll_runtime_seconds = 300
sync_hash_import_enabled = true
sync_hash_import_path = /nightfall/media/pictures
sync_hash_import_glob = .hashes.sha1
"""
            + core_extra
            + """

[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid-primary
onedrive_root = /Camera Roll
token_cache = /tmp/primary.token
delta_cursor = /tmp/primary.cursor
"""
        ).strip(),
        encoding="utf-8",
    )
    return cfg


def test_v2_integrity_mode_parses_when_valid(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "\nintegrity_mode = tolerant\n")
    parsed = load_config(cfg)
    assert parsed.core.integrity_mode == "tolerant"


def test_v2_integrity_mode_rejects_invalid_value(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "\nintegrity_mode = permissive\n")
    with pytest.raises(ConfigError, match="integrity_mode"):
        load_config(cfg)


def test_v2_drift_thresholds_validate_ordering(tmp_path: Path) -> None:
    cfg = _write_config(
        tmp_path,
        "\ndrift_warning_threshold_ratio = 0.5\ndrift_critical_threshold_ratio = 0.1\n",
    )
    with pytest.raises(ConfigError, match="drift_warning_threshold_ratio"):
        load_config(cfg)


def test_v2_delta_loop_resync_threshold_must_be_positive(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "\ndelta_loop_resync_threshold = 0\n")
    with pytest.raises(ConfigError, match="delta_loop_resync_threshold"):
        load_config(cfg)


def test_v2_delta_breaker_thresholds_must_be_positive(tmp_path: Path) -> None:
    cfg = _write_config(
        tmp_path,
        "\ndelta_breaker_ghost_threshold = 0\ndelta_breaker_stale_page_threshold = -1\n",
    )
    with pytest.raises(ConfigError, match="delta_breaker_ghost_threshold"):
        load_config(cfg)


def test_v2_delta_breaker_cooldown_must_be_positive(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "\ndelta_breaker_cooldown_seconds = 0\n")
    with pytest.raises(ConfigError, match="delta_breaker_cooldown_seconds"):
        load_config(cfg)


def test_v2_account_worker_count_must_be_positive(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, "\naccount_worker_count = 0\n")
    with pytest.raises(ConfigError, match="account_worker_count"):
        load_config(cfg)


def test_v2_backpressure_thresholds_must_be_positive(tmp_path: Path) -> None:
    cfg = _write_config(
        tmp_path,
        (
            "\nbackpressure_retry_threshold = 0"
            "\nbackpressure_transport_error_threshold = 0"
            "\nbackpressure_cooldown_seconds = 0\n"
        ),
    )
    with pytest.raises(ConfigError, match="backpressure_retry_threshold"):
        load_config(cfg)
