"""Integration tests for the config-check CLI command (Module 1)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _write_config(tmp_path: Path, body: str, name: str = "photo-ingress.conf") -> Path:
    """Write config content to a file and return path."""

    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _valid_config_body() -> str:
    """Return a valid minimal configuration file body."""

    return """
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

[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid-primary
onedrive_root = /Camera Roll
token_cache = /tmp/primary.token
delta_cursor = /tmp/primary.cursor
""".strip()


def test_config_check_valid_config_exits_zero(tmp_path: Path) -> None:
    """config-check should pass for a valid configuration file."""

    cfg = _write_config(tmp_path, _valid_config_body())

    result = subprocess.run(
        [sys.executable, "-m", "nightfall_photo_ingress", "config-check", "--path", str(cfg)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0


def test_config_check_invalid_config_exits_non_zero_and_prints_errors(tmp_path: Path) -> None:
    """config-check should fail with actionable diagnostics for invalid config."""

    cfg = _write_config(tmp_path, "[core]\nconfig_version = 99")

    result = subprocess.run(
        [sys.executable, "-m", "nightfall_photo_ingress", "config-check", "--path", str(cfg)],
        capture_output=True,
        text=True,
        check=False,
    )

    merged_output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "ERROR:" in merged_output
    assert "config_version" in merged_output
