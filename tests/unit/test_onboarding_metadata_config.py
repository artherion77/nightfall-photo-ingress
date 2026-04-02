"""Tests for onboarding metadata integration in config loading and CLI helpers."""

from __future__ import annotations

import json
from pathlib import Path

from nightfall_photo_ingress import cli
from nightfall_photo_ingress.config import load_config


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "photo-ingress.conf"
    cfg.write_text(
        f"""
[core]
config_version = 2
poll_interval_minutes = 15
process_accounts_in_config_order = true
staging_path = {tmp_path / 'staging'}
pending_path = {tmp_path / 'pending'}
accepted_path = {tmp_path / 'accepted'}
rejected_path = {tmp_path / 'rejected'}
trash_path = {tmp_path / 'trash'}
registry_path = {tmp_path / 'registry.db'}
staging_on_same_pool = false
storage_template = {{yyyy}}/{{mm}}/{{original}}
verify_sha256_on_first_download = true
max_downloads_per_poll = 100
max_poll_runtime_seconds = 300
sync_hash_import_enabled = true
sync_hash_import_path = {tmp_path / 'pictures'}
sync_hash_import_glob = .hashes.sha1

[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid-primary
onedrive_root = /Camera Roll
token_cache = {tmp_path / 'primary.token.json'}
delta_cursor = {tmp_path / 'primary.cursor'}
""".strip(),
        encoding="utf-8",
    )
    return cfg


def test_load_config_prefers_onboarding_resolved_root(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    metadata_path = tmp_path / "primary.token.json.onboarding.json"
    metadata_path.write_text(
        json.dumps({"resolved_onedrive_root": "/Bilder/Eigene Aufnahmen"}),
        encoding="utf-8",
    )

    parsed = load_config(cfg)
    account = parsed.accounts[0]

    assert account.onedrive_root == "/Camera Roll"
    assert account.resolved_onedrive_root == "/Bilder/Eigene Aufnahmen"
    assert account.effective_onedrive_root == "/Bilder/Eigene Aufnahmen"


def test_write_account_onedrive_root_updates_section_value(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)

    ok = cli._write_account_onedrive_root(str(cfg), "primary", "/Bilder/Eigene Aufnahmen")

    assert ok is True
    parsed = load_config(cfg)
    assert parsed.accounts[0].onedrive_root == "/Bilder/Eigene Aufnahmen"


def test_load_config_migrates_legacy_onboarding_sidecar_name(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    legacy_metadata_path = tmp_path / "primary.token.json.onboarding.json"
    migrated_metadata_path = tmp_path / "primary.token.onboarding.json"
    legacy_metadata_path.write_text(
        json.dumps({"resolved_onedrive_root": "/Bilder/Eigene Aufnahmen"}),
        encoding="utf-8",
    )

    parsed = load_config(cfg)
    account = parsed.accounts[0]

    assert account.resolved_onedrive_root == "/Bilder/Eigene Aufnahmen"
    assert migrated_metadata_path.exists()
    assert not legacy_metadata_path.exists()
