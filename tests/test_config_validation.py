"""Config validation tests for Module 1."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightfall_photo_ingress.config import ConfigError, load_config, validate_config_file


def _write_config(tmp_path: Path, body: str) -> Path:
    """Create a config file for tests."""

    cfg = tmp_path / "photo-ingress.conf"
    cfg.write_text(body, encoding="utf-8")
    return cfg


def _base_core() -> str:
    """Return a minimal valid [core] section."""

    return """
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
""".strip()


def _account(name: str, *, provider: str = "onedrive", token_cache: str = "/tmp/t.token", delta_cursor: str = "/tmp/t.cursor") -> str:
    """Return one account section string."""

    return f"""
[account.{name}]
enabled = true
provider = {provider}
authority = https://login.microsoftonline.com/consumers
client_id = cid-{name}
onedrive_root = /Camera Roll
token_cache = {token_cache}
delta_cursor = {delta_cursor}
""".strip()


def test_missing_required_key_fails(tmp_path: Path) -> None:
    """Missing required core keys should fail validation."""

    cfg = _write_config(
        tmp_path,
        """
[core]
config_version = 1
poll_interval_minutes = 15
""".strip()
        + "\n\n"
        + _account("primary"),
    )

    with pytest.raises(ConfigError) as exc:
        load_config(cfg)

    assert "missing required key: staging_path" in str(exc.value)


def test_unsupported_provider_rejected(tmp_path: Path) -> None:
    """Provider must be onedrive in V1."""

    cfg = _write_config(
        tmp_path,
        _base_core() + "\n\n" + _account("primary", provider="dropbox"),
    )

    with pytest.raises(ConfigError) as exc:
        load_config(cfg)

    assert "provider must be 'onedrive'" in str(exc.value)


def test_invalid_account_name_rejected(tmp_path: Path) -> None:
    """Account section name must match required pattern."""

    cfg = _write_config(
        tmp_path,
        _base_core()
        + "\n\n"
        + """
[account.Primary User]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid
onedrive_root = /Camera Roll
token_cache = /tmp/one.token
delta_cursor = /tmp/one.cursor
""".strip(),
    )

    with pytest.raises(ConfigError) as exc:
        load_config(cfg)

    assert "Account name must match" in str(exc.value)


def test_duplicate_token_cache_and_delta_cursor_rejected(tmp_path: Path) -> None:
    """Token and cursor files must be unique per account."""

    cfg = _write_config(
        tmp_path,
        _base_core()
        + "\n\n"
        + _account("a", token_cache="/tmp/shared.token", delta_cursor="/tmp/shared.cursor")
        + "\n\n"
        + _account("b", token_cache="/tmp/shared.token", delta_cursor="/tmp/shared.cursor"),
    )

    with pytest.raises(ConfigError) as exc:
        load_config(cfg)

    message = str(exc.value)
    assert "Duplicate token_cache path" in message
    assert "Duplicate delta_cursor path" in message


def test_live_photo_enum_validation_rejects_invalid_values(tmp_path: Path) -> None:
    """V1 accepts only the documented default enum values."""

    cfg = _write_config(
        tmp_path,
        _base_core().replace("live_photo_stem_mode = exact_stem\n", "")
        + "\n"
        + "live_photo_stem_mode = fuzzy_stem\n"
        + "live_photo_component_order = motion_first\n"
        + "live_photo_conflict_policy = first_seen\n\n"
        + _account("primary"),
    )

    with pytest.raises(ConfigError) as exc:
        load_config(cfg)

    text = str(exc.value)
    assert "live_photo_stem_mode" in text
    assert "live_photo_component_order" in text
    assert "live_photo_conflict_policy" in text


def test_validate_config_file_returns_diagnostics(tmp_path: Path) -> None:
    """validate_config_file should return readable diagnostics, not raise."""

    cfg = _write_config(tmp_path, "[core]\nconfig_version = 99")
    errors = validate_config_file(cfg)

    assert errors
    assert any("config_version" in error for error in errors)
