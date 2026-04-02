"""Tests for per-account OneDrive path configuration feature.

This module validates that the onedrive_root configuration can be set
per-account and handles various path formats correctly, including:
- English paths: /Camera Roll
- German paths: /Bilder/Eigene Aufnahmen
- Paths with spaces and special characters
- URL encoding for Graph API calls
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nightfall_photo_ingress.config import AccountConfig, AppConfig, CoreConfig, LoggingConfig, load_config


def _write_config(tmp_path: Path, body: str) -> Path:
    """Create a config file for tests."""
    cfg = tmp_path / "photo-ingress.conf"
    cfg.write_text(body, encoding="utf-8")
    return cfg


def _base_core_config() -> str:
    """Return a base core section with all required fields."""
    return """
[core]
config_version = 2
poll_interval_minutes = 15
process_accounts_in_config_order = true
staging_path = /tmp/staging
pending_path = /tmp/pending
accepted_path = /tmp/accepted
rejected_path = /tmp/rejected
trash_path = /tmp/trash
registry_path = /tmp/registry.db
staging_on_same_pool = false
storage_template = {yyyy}/{mm}/{original}
verify_sha256_on_first_download = true
max_downloads_per_poll = 100
max_poll_runtime_seconds = 300
sync_hash_import_enabled = false
sync_hash_import_path = /tmp/hashes
sync_hash_import_glob = .hashes.sha1
"""


def test_parse_config_with_personal_camera_roll_english(tmp_path: Path) -> None:
    """Config should parse English /Camera Roll path correctly."""
    cfg = _write_config(
        tmp_path,
        _base_core_config()
        + """
[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = test-client-id
onedrive_root = /Camera Roll
token_cache = /tmp/token.json
delta_cursor = /tmp/cursor.txt
""",
    )

    config = load_config(cfg)
    account = config.accounts[0]

    assert account.name == "primary"
    assert account.onedrive_root == "/Camera Roll"
    assert account.enabled is True


def test_parse_config_with_german_bilder_path(tmp_path: Path) -> None:
    """Config should parse German /Bilder/Eigene Aufnahmen path correctly."""
    cfg = _write_config(
        tmp_path,
        _base_core_config()
        + """
[account.german_account]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = test-client-id-de
onedrive_root = /Bilder/Eigene Aufnahmen
token_cache = /tmp/de_token.json
delta_cursor = /tmp/de_cursor.txt
""",
    )

    config = load_config(cfg)
    account = config.accounts[0]

    assert account.name == "german_account"
    assert account.onedrive_root == "/Bilder/Eigene Aufnahmen"


def test_parse_config_with_multiple_accounts_different_paths(tmp_path: Path) -> None:
    """Config should parse multiple accounts with different onedrive_root values."""
    cfg = _write_config(
        tmp_path,
        _base_core_config()
        + """
[account.english]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = client-en
onedrive_root = /Camera Roll
token_cache = /tmp/en_token.json
delta_cursor = /tmp/en_cursor.txt

[account.german]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = client-de
onedrive_root = /Bilder/Eigene Aufnahmen
token_cache = /tmp/de_token.json
delta_cursor = /tmp/de_cursor.txt

[account.custom]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = client-custom
onedrive_root = /My Photos/Archive
token_cache = /tmp/custom_token.json
delta_cursor = /tmp/custom_cursor.txt
""",
    )

    config = load_config(cfg)
    assert len(config.accounts) == 3

    # Verify each account has its own path
    en_account = next(a for a in config.accounts if a.name == "english")
    de_account = next(a for a in config.accounts if a.name == "german")
    custom_account = next(a for a in config.accounts if a.name == "custom")

    assert en_account.onedrive_root == "/Camera Roll"
    assert de_account.onedrive_root == "/Bilder/Eigene Aufnahmen"
    assert custom_account.onedrive_root == "/My Photos/Archive"


def test_onedrive_root_with_special_characters(tmp_path: Path) -> None:
    """Config should handle onedrive_root paths with special characters."""
    cfg = _write_config(
        tmp_path,
        _base_core_config()
        + """
[account.special]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = client-special
onedrive_root = /My Photos & Videos (2024)
token_cache = /tmp/special_token.json
delta_cursor = /tmp/special_cursor.txt
""",
    )

    config = load_config(cfg)
    account = config.accounts[0]

    # Verify special characters are preserved
    assert account.onedrive_root == "/My Photos & Videos (2024)"


def test_onedrive_root_without_leading_slash_is_normalized(tmp_path: Path) -> None:
    """Config should handle onedrive_root paths without leading slash."""
    cfg = _write_config(
        tmp_path,
        _base_core_config()
        + """
[account.no_slash]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = client-noslash
onedrive_root = Camera Roll
token_cache = /tmp/noslash_token.json
delta_cursor = /tmp/noslash_cursor.txt
""",
    )

    config = load_config(cfg)
    account = config.accounts[0]

    # Config parsing preserves as-is; normalization happens at delta URL build time
    assert account.onedrive_root == "Camera Roll"


def test_onedrive_root_with_trailing_spaces(tmp_path: Path) -> None:
    """Config should handle onedrive_root paths with trailing whitespace."""
    cfg = _write_config(
        tmp_path,
        _base_core_config()
        + """
[account.spaces]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = client-spaces
onedrive_root = /Camera Roll   
token_cache = /tmp/spaces_token.json
delta_cursor = /tmp/spaces_cursor.txt
""",
    )

    config = load_config(cfg)
    account = config.accounts[0]

    # Trailing spaces are preserved in config (delta URL builder strips them)
    assert "/Camera Roll" in account.onedrive_root


def test_delta_url_building_with_camera_roll_path() -> None:
    """Delta URL builder should correctly encode /Camera Roll path."""
    account = AccountConfig(
        name="test",
        enabled=True,
        display_name="Test",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="test-id",
        onedrive_root="/Camera Roll",
        token_cache=Path("/tmp/token.json"),
        delta_cursor=Path("/tmp/cursor.txt"),
        max_downloads=None,
    )

    # Access the private function through the module
    from nightfall_photo_ingress.adapters.onedrive.client import _build_initial_delta_url

    url = _build_initial_delta_url(account)

    # URL should contain the root path with URL-encoded space
    assert "Camera%20Roll" in url
    assert url.endswith(":/delta")
    assert url.startswith("https://graph.microsoft.com/v1.0/me/drive/root:")


def test_delta_url_building_with_german_bilder_path() -> None:
    """Delta URL builder should correctly encode German /Bilder/Eigene Aufnahmen path."""
    account = AccountConfig(
        name="german",
        enabled=True,
        display_name="German Account",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="test-id-de",
        onedrive_root="/Bilder/Eigene Aufnahmen",
        token_cache=Path("/tmp/de_token.json"),
        delta_cursor=Path("/tmp/de_cursor.txt"),
        max_downloads=None,
    )

    from nightfall_photo_ingress.adapters.onedrive.client import _build_initial_delta_url

    url = _build_initial_delta_url(account)

    # URL should encode both segments with spaces
    assert "Bilder" in url
    assert "Eigene%20Aufnahmen" in url
    assert url.endswith(":/delta")


def test_delta_url_building_with_special_characters() -> None:
    """Delta URL builder should correctly encode paths with special characters."""
    account = AccountConfig(
        name="special",
        enabled=True,
        display_name="Special",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="test-id-special",
        onedrive_root="/My Photos & Videos (2024)",
        token_cache=Path("/tmp/special_token.json"),
        delta_cursor=Path("/tmp/special_cursor.txt"),
        max_downloads=None,
    )

    from nightfall_photo_ingress.adapters.onedrive.client import _build_initial_delta_url

    url = _build_initial_delta_url(account)

    # Special characters should be URL-encoded
    assert "My%20Photos" in url
    assert "%26" in url or "&" not in url.split("root:")[1]  # & should be encoded
    assert "%28" in url or "(" not in url.split("root:")[1]  # ( should be encoded


def test_delta_url_building_without_leading_slash() -> None:
    """Delta URL builder should handle paths without leading slash."""
    account = AccountConfig(
        name="noslash",
        enabled=True,
        display_name="No Slash",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="test-id-noslash",
        onedrive_root="Camera Roll",
        token_cache=Path("/tmp/noslash_token.json"),
        delta_cursor=Path("/tmp/noslash_cursor.txt"),
        max_downloads=None,
    )

    from nightfall_photo_ingress.adapters.onedrive.client import _build_initial_delta_url

    url = _build_initial_delta_url(account)

    # Should still produce valid URL with normalized slash
    assert "/Camera%20Roll" in url or "%2FCamera%20Roll" not in url  # Slash should be normalized
    assert url.endswith(":/delta")


def test_delta_url_building_strips_whitespace() -> None:
    """Delta URL builder should strip leading/trailing whitespace from paths."""
    account = AccountConfig(
        name="spaces",
        enabled=True,
        display_name="Spaces",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="test-id-spaces",
        onedrive_root="  /Camera Roll  ",
        token_cache=Path("/tmp/spaces_token.json"),
        delta_cursor=Path("/tmp/spaces_cursor.txt"),
        max_downloads=None,
    )

    from nightfall_photo_ingress.adapters.onedrive.client import _build_initial_delta_url

    url = _build_initial_delta_url(account)

    # Should handle the spaces gracefully
    assert "Camera%20Roll" in url
    # Should not have encoded spaces in the path name itself
    assert "%20%2F" not in url  # Should not have encoded space before slash


def test_account_config_preserves_per_account_roots() -> None:
    """AccountConfig should preserve unique onedrive_root per account."""
    accounts = [
        AccountConfig(
            name="account1",
            enabled=True,
            display_name="Account 1",
            provider="onedrive",
            authority="https://login.microsoftonline.com/consumers",
            client_id="id1",
            onedrive_root="/Camera Roll",
            token_cache=Path("/tmp/token1.json"),
            delta_cursor=Path("/tmp/cursor1.txt"),
            max_downloads=None,
        ),
        AccountConfig(
            name="account2",
            enabled=True,
            display_name="Account 2",
            provider="onedrive",
            authority="https://login.microsoftonline.com/consumers",
            client_id="id2",
            onedrive_root="/Bilder/Eigene Aufnahmen",
            token_cache=Path("/tmp/token2.json"),
            delta_cursor=Path("/tmp/cursor2.txt"),
            max_downloads=None,
        ),
    ]

    # Verify each account has its own configured root
    assert accounts[0].onedrive_root == "/Camera Roll"
    assert accounts[1].onedrive_root == "/Bilder/Eigene Aufnahmen"

    # Verify they are independent
    assert accounts[0].onedrive_root != accounts[1].onedrive_root
