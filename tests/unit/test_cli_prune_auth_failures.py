from __future__ import annotations

import sqlite3
from pathlib import Path

from nightfall_photo_ingress import cli
from nightfall_photo_ingress.domain.registry import Registry


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "photo-ingress.conf"
    cfg.write_text(
        f"""
[core]
config_version = 2
poll_interval_minutes = 720
process_accounts_in_config_order = true
staging_path = {tmp_path / 'staging'}
pending_path = {tmp_path / 'pending'}
accepted_path = {tmp_path / 'accepted'}
accepted_storage_template = {{yyyy}}/{{mm}}/{{original}}
rejected_path = {tmp_path / 'rejected'}
trash_path = {tmp_path / 'trash'}
registry_path = {tmp_path / 'registry.db'}
staging_on_same_pool = false
storage_template = {{yyyy}}/{{mm}}/{{original}}
verify_sha256_on_first_download = true
max_downloads_per_poll = 200
max_poll_runtime_seconds = 300
sync_hash_import_enabled = true
sync_hash_import_path = {tmp_path / 'pictures'}
sync_hash_import_glob = .hashes.sha1

[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid
onedrive_root = /Camera Roll
token_cache = {tmp_path / 'primary.token'}
delta_cursor = {tmp_path / 'primary.cursor'}
""".strip(),
        encoding="utf-8",
    )
    return cfg


def test_cli_prune_auth_failures_creates_backup_and_prunes_rows(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    backup_path = tmp_path / "registry-pre-prune.bak"

    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.append_audit_event(
        sha256=None,
        action="auth_failure",
        reason="Missing Authorization header",
        actor="api_auth",
    )
    registry.append_audit_event(
        sha256="a" * 64,
        action="accepted",
        reason="ok",
        actor="operator",
    )

    exit_code = cli.main([
        "prune-auth-failures",
        "--path",
        str(cfg),
        "--backup-path",
        str(backup_path),
        "--keep-latest",
        "0",
    ])

    assert exit_code == 0
    assert backup_path.exists()

    with sqlite3.connect(registry.db_path) as conn:
        auth_count = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'auth_failure'").fetchone()[0]
        accepted_count = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'accepted'").fetchone()[0]

    assert auth_count == 0
    assert accepted_count == 1