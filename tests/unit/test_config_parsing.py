"""Config parsing tests for Module 1."""

from __future__ import annotations

from pathlib import Path

from nightfall_photo_ingress.config import load_config


def _write_config(tmp_path: Path, body: str) -> Path:
    """Create a config file for tests."""

    cfg = tmp_path / "photo-ingress.conf"
    cfg.write_text(body, encoding="utf-8")
    return cfg


def test_parse_valid_config_and_preserve_account_order(tmp_path: Path) -> None:
    """Parser should load a valid config and preserve declaration order."""

    cfg = _write_config(
        tmp_path,
        """
[core]
config_version = 1
poll_interval_minutes = 15
process_accounts_in_config_order = true
staging_path = /mnt/ssd/photo-ingress/staging
accepted_path = /nightfall/media/photo-ingress/accepted
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

[account.zeta]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid-1
onedrive_root = /Camera Roll
token_cache = /tmp/zeta.token
delta_cursor = /tmp/zeta.cursor

[account.alpha]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid-2
onedrive_root = /Camera Roll
token_cache = /tmp/alpha.token
delta_cursor = /tmp/alpha.cursor

[logging]
log_level = INFO
console_format = json
""".strip(),
    )

    parsed = load_config(cfg)

    assert [account.name for account in parsed.accounts] == ["zeta", "alpha"]
    assert [account.name for account in parsed.ordered_enabled_accounts()] == ["zeta", "alpha"]
    assert parsed.core.verify_sha256_on_first_download is True
    assert parsed.core.live_photo_capture_tolerance_seconds == 3


def test_process_accounts_in_config_order_false_sorts_enabled_accounts(tmp_path: Path) -> None:
    """When disabled, order helper should return name-sorted enabled accounts."""

    cfg = _write_config(
        tmp_path,
        """
[core]
config_version = 1
poll_interval_minutes = 15
process_accounts_in_config_order = false
staging_path = /mnt/ssd/photo-ingress/staging
accepted_path = /nightfall/media/photo-ingress/accepted
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

[account.zeta]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid-1
onedrive_root = /Camera Roll
token_cache = /tmp/zeta.token
delta_cursor = /tmp/zeta.cursor

[account.alpha]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid-2
onedrive_root = /Camera Roll
token_cache = /tmp/alpha.token
delta_cursor = /tmp/alpha.cursor
""".strip(),
    )

    parsed = load_config(cfg)

    assert [account.name for account in parsed.ordered_enabled_accounts()] == ["alpha", "zeta"]


def test_verify_sha256_bool_parsing(tmp_path: Path) -> None:
    """Boolean parser should handle explicit false for verification flag."""

    cfg = _write_config(
        tmp_path,
        """
[core]
config_version = 1
poll_interval_minutes = 15
process_accounts_in_config_order = true
staging_path = /mnt/ssd/photo-ingress/staging
accepted_path = /nightfall/media/photo-ingress/accepted
trash_path = /nightfall/media/photo-ingress/trash
registry_path = /mnt/ssd/photo-ingress/registry.db
staging_on_same_pool = false
storage_template = {yyyy}/{mm}/{sha8}-{original}
verify_sha256_on_first_download = false
max_downloads_per_poll = 200
max_poll_runtime_seconds = 300
sync_hash_import_enabled = true
sync_hash_import_path = /nightfall/media/pictures
sync_hash_import_glob = .hashes.sha1

[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid
onedrive_root = /Camera Roll
token_cache = /tmp/primary.token
delta_cursor = /tmp/primary.cursor
""".strip(),
    )

    parsed = load_config(cfg)

    assert parsed.core.verify_sha256_on_first_download is False


def test_storage_template_defaults_to_canonical_v1_when_omitted(tmp_path: Path) -> None:
    """Default accepted queue layout should match canonical V1 template."""

    cfg = _write_config(
        tmp_path,
        """
[core]
config_version = 1
poll_interval_minutes = 15
process_accounts_in_config_order = true
staging_path = /mnt/ssd/photo-ingress/staging
accepted_path = /nightfall/media/photo-ingress/accepted
trash_path = /nightfall/media/photo-ingress/trash
registry_path = /mnt/ssd/photo-ingress/registry.db
staging_on_same_pool = false
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
client_id = cid
onedrive_root = /Camera Roll
token_cache = /tmp/primary.token
delta_cursor = /tmp/primary.cursor
""".strip(),
    )

    parsed = load_config(cfg)

    assert parsed.core.storage_template == "{yyyy}/{mm}/{original}"
