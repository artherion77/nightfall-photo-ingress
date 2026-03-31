"""Configuration model and validation for Module 1.

This module parses the INI configuration file and validates supported keys for
V1. It returns typed dataclasses so downstream modules can consume config safely.
"""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_CONFIG_VERSION = 1
ACCOUNT_NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")
SUPPORTED_PROVIDER = "onedrive"
SUPPORTED_STEM_MODE = {"exact_stem"}
SUPPORTED_COMPONENT_ORDER = {"photo_first"}
SUPPORTED_CONFLICT_POLICY = {"nearest_capture_time"}
SUPPORTED_INTEGRITY_MODES = {"strict", "tolerant"}


class ConfigError(ValueError):
    """Raised when configuration parsing or validation fails."""


@dataclass(frozen=True)
class CoreConfig:
    """Top-level core settings shared by all adapters and accounts."""

    config_version: int
    poll_interval_minutes: int
    process_accounts_in_config_order: bool
    staging_path: Path
    accepted_path: Path
    trash_path: Path
    registry_path: Path
    staging_on_same_pool: bool
    storage_template: str
    verify_sha256_on_first_download: bool
    max_downloads_per_poll: int
    max_poll_runtime_seconds: int
    tmp_ttl_minutes: int
    failed_ttl_hours: int
    orphan_ttl_days: int
    live_photo_capture_tolerance_seconds: int
    live_photo_stem_mode: str
    live_photo_component_order: str
    live_photo_conflict_policy: str
    sync_hash_import_enabled: bool
    sync_hash_import_path: Path
    sync_hash_import_glob: str
    integrity_mode: str = "strict"
    drift_warning_threshold_ratio: float = 0.05
    drift_critical_threshold_ratio: float = 0.20
    drift_min_events_for_evaluation: int = 20
    drift_fail_fast_enabled: bool = True
    delta_loop_resync_threshold: int = 3
    delta_breaker_ghost_threshold: int = 10
    delta_breaker_stale_page_threshold: int = 10
    delta_breaker_cooldown_seconds: int = 300


@dataclass(frozen=True)
class LoggingConfig:
    """Optional logging overrides loaded from the INI file."""

    log_level: str = "INFO"
    console_format: str = "json"


@dataclass(frozen=True)
class AccountConfig:
    """Configuration for one source account section."""

    name: str
    enabled: bool
    display_name: str
    provider: str
    authority: str
    client_id: str
    onedrive_root: str
    token_cache: Path
    delta_cursor: Path
    max_downloads: int | None


@dataclass(frozen=True)
class AppConfig:
    """Root configuration object returned by the parser."""

    source_path: Path
    core: CoreConfig
    logging: LoggingConfig
    accounts: tuple[AccountConfig, ...]

    def ordered_enabled_accounts(self) -> tuple[AccountConfig, ...]:
        """Return enabled accounts based on configured ordering policy.

        When `process_accounts_in_config_order` is true, declaration order from
        the config file is preserved. If false, accounts are sorted by name.
        """

        enabled = tuple(account for account in self.accounts if account.enabled)
        if self.core.process_accounts_in_config_order:
            return enabled
        return tuple(sorted(enabled, key=lambda account: account.name))


def validate_config_file(path: Path | str) -> list[str]:
    """Validate the configuration file and return human-readable diagnostics.

    The function returns an empty list when the config is valid.
    """

    try:
        load_config(path)
        return []
    except ConfigError as exc:
        return str(exc).splitlines()


def load_config(path: Path | str) -> AppConfig:
    """Parse and validate an INI config file.

    Args:
        path: Path to the INI file.

    Raises:
        ConfigError: If parsing fails or validation errors are found.
    """

    cfg_path = Path(path)
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str

    try:
        with cfg_path.open("r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {cfg_path}") from exc
    except OSError as exc:
        raise ConfigError(f"Unable to read config file: {cfg_path}: {exc}") from exc

    errors: list[str] = []
    core = _parse_core(parser, errors)
    logging_cfg = _parse_logging(parser, errors)
    accounts = _parse_accounts(parser, core.max_downloads_per_poll, errors)

    _validate_accounts(accounts, errors)
    _validate_core(core, errors)

    if errors:
        raise ConfigError("\n".join(errors))

    return AppConfig(
        source_path=cfg_path,
        core=core,
        logging=logging_cfg,
        accounts=tuple(accounts),
    )


def _parse_core(parser: configparser.ConfigParser, errors: list[str]) -> CoreConfig:
    """Parse and validate required and optional values from [core]."""

    section = "core"
    if section not in parser:
        errors.append("Missing required [core] section")
        return _default_core()

    core = parser[section]

    return CoreConfig(
        config_version=_get_int(core, "config_version", errors, required=True),
        poll_interval_minutes=_get_int(core, "poll_interval_minutes", errors, default=15),
        process_accounts_in_config_order=_get_bool(
            core,
            "process_accounts_in_config_order",
            errors,
            default=True,
        ),
        staging_path=_get_path(core, "staging_path", errors, required=True),
        accepted_path=_get_path(core, "accepted_path", errors, required=True),
        trash_path=_get_path(core, "trash_path", errors, required=True),
        registry_path=_get_path(core, "registry_path", errors, required=True),
        staging_on_same_pool=_get_bool(core, "staging_on_same_pool", errors, default=False),
        storage_template=_get_str(
            core,
            "storage_template",
            errors,
            default="{yyyy}/{mm}/{sha8}-{original}",
        ),
        verify_sha256_on_first_download=_get_bool(
            core,
            "verify_sha256_on_first_download",
            errors,
            default=True,
        ),
        max_downloads_per_poll=_get_int(core, "max_downloads_per_poll", errors, default=200),
        max_poll_runtime_seconds=_get_int(core, "max_poll_runtime_seconds", errors, default=300),
        tmp_ttl_minutes=_get_int(core, "tmp_ttl_minutes", errors, default=120),
        failed_ttl_hours=_get_int(core, "failed_ttl_hours", errors, default=24),
        orphan_ttl_days=_get_int(core, "orphan_ttl_days", errors, default=7),
        live_photo_capture_tolerance_seconds=_get_int(
            core,
            "live_photo_capture_tolerance_seconds",
            errors,
            default=3,
        ),
        live_photo_stem_mode=_get_str(core, "live_photo_stem_mode", errors, default="exact_stem"),
        live_photo_component_order=_get_str(
            core,
            "live_photo_component_order",
            errors,
            default="photo_first",
        ),
        live_photo_conflict_policy=_get_str(
            core,
            "live_photo_conflict_policy",
            errors,
            default="nearest_capture_time",
        ),
        sync_hash_import_enabled=_get_bool(core, "sync_hash_import_enabled", errors, default=True),
        sync_hash_import_path=_get_path(core, "sync_hash_import_path", errors, required=True),
        sync_hash_import_glob=_get_str(core, "sync_hash_import_glob", errors, default=".hashes.sha1"),
        integrity_mode=_get_str(core, "integrity_mode", errors, default="strict"),
        drift_warning_threshold_ratio=_get_float(
            core,
            "drift_warning_threshold_ratio",
            errors,
            default=0.05,
        ),
        drift_critical_threshold_ratio=_get_float(
            core,
            "drift_critical_threshold_ratio",
            errors,
            default=0.20,
        ),
        drift_min_events_for_evaluation=_get_int(
            core,
            "drift_min_events_for_evaluation",
            errors,
            default=20,
        ),
        drift_fail_fast_enabled=_get_bool(
            core,
            "drift_fail_fast_enabled",
            errors,
            default=True,
        ),
        delta_loop_resync_threshold=_get_int(
            core,
            "delta_loop_resync_threshold",
            errors,
            default=3,
        ),
        delta_breaker_ghost_threshold=_get_int(
            core,
            "delta_breaker_ghost_threshold",
            errors,
            default=10,
        ),
        delta_breaker_stale_page_threshold=_get_int(
            core,
            "delta_breaker_stale_page_threshold",
            errors,
            default=10,
        ),
        delta_breaker_cooldown_seconds=_get_int(
            core,
            "delta_breaker_cooldown_seconds",
            errors,
            default=300,
        ),
    )


def _default_core() -> CoreConfig:
    """Return fallback defaults used only after [core] parse failure."""

    return CoreConfig(
        config_version=SUPPORTED_CONFIG_VERSION,
        poll_interval_minutes=15,
        process_accounts_in_config_order=True,
        staging_path=Path("/tmp/staging"),
        accepted_path=Path("/tmp/accepted"),
        trash_path=Path("/tmp/trash"),
        registry_path=Path("/tmp/registry.db"),
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
        sync_hash_import_path=Path("/nightfall/media/pictures"),
        sync_hash_import_glob=".hashes.sha1",
        integrity_mode="strict",
        drift_warning_threshold_ratio=0.05,
        drift_critical_threshold_ratio=0.20,
        drift_min_events_for_evaluation=20,
        drift_fail_fast_enabled=True,
        delta_loop_resync_threshold=3,
        delta_breaker_ghost_threshold=10,
        delta_breaker_stale_page_threshold=10,
        delta_breaker_cooldown_seconds=300,
    )


def _parse_logging(parser: configparser.ConfigParser, errors: list[str]) -> LoggingConfig:
    """Parse optional [logging] values and apply defaults."""

    if "logging" not in parser:
        return LoggingConfig()

    section = parser["logging"]
    return LoggingConfig(
        log_level=_get_str(section, "log_level", errors, default="INFO").upper(),
        console_format=_get_str(section, "console_format", errors, default="json"),
    )


def _parse_accounts(
    parser: configparser.ConfigParser,
    inherited_max_downloads: int,
    errors: list[str],
) -> list[AccountConfig]:
    """Parse account sections in declaration order."""

    accounts: list[AccountConfig] = []

    for section_name in parser.sections():
        if not section_name.startswith("account."):
            continue

        account_name = section_name[len("account.") :]
        section = parser[section_name]

        account = AccountConfig(
            name=account_name,
            enabled=_get_bool(section, "enabled", errors, default=True),
            display_name=_get_str(section, "display_name", errors, default=account_name),
            provider=_get_str(section, "provider", errors, required=True),
            authority=_get_str(
                section,
                "authority",
                errors,
                default="https://login.microsoftonline.com/consumers",
            ),
            client_id=_get_str(section, "client_id", errors, required=True),
            onedrive_root=_get_str(section, "onedrive_root", errors, required=True),
            token_cache=_get_path(section, "token_cache", errors, required=True),
            delta_cursor=_get_path(section, "delta_cursor", errors, required=True),
            max_downloads=_get_optional_int(
                section,
                "max_downloads",
                errors,
                default=inherited_max_downloads,
            ),
        )
        accounts.append(account)

    return accounts


def _validate_core(core: CoreConfig, errors: list[str]) -> None:
    """Validate cross-field [core] rules."""

    if core.config_version != SUPPORTED_CONFIG_VERSION:
        errors.append(
            "[core] config_version must be "
            f"{SUPPORTED_CONFIG_VERSION}; got {core.config_version}"
        )

    if core.poll_interval_minutes <= 0:
        errors.append("[core] poll_interval_minutes must be > 0")

    if core.max_downloads_per_poll <= 0:
        errors.append("[core] max_downloads_per_poll must be > 0")

    if core.max_poll_runtime_seconds <= 0:
        errors.append("[core] max_poll_runtime_seconds must be > 0")

    if core.live_photo_capture_tolerance_seconds < 0:
        errors.append("[core] live_photo_capture_tolerance_seconds must be >= 0")

    if core.live_photo_stem_mode not in SUPPORTED_STEM_MODE:
        errors.append(
            "[core] live_photo_stem_mode must be one of: "
            f"{sorted(SUPPORTED_STEM_MODE)}"
        )

    if core.live_photo_component_order not in SUPPORTED_COMPONENT_ORDER:
        errors.append(
            "[core] live_photo_component_order must be one of: "
            f"{sorted(SUPPORTED_COMPONENT_ORDER)}"
        )

    if core.live_photo_conflict_policy not in SUPPORTED_CONFLICT_POLICY:
        errors.append(
            "[core] live_photo_conflict_policy must be one of: "
            f"{sorted(SUPPORTED_CONFLICT_POLICY)}"
        )

    if core.integrity_mode not in SUPPORTED_INTEGRITY_MODES:
        errors.append(
            "[core] integrity_mode must be one of: "
            f"{sorted(SUPPORTED_INTEGRITY_MODES)}"
        )

    if core.drift_warning_threshold_ratio < 0:
        errors.append("[core] drift_warning_threshold_ratio must be >= 0")

    if core.drift_critical_threshold_ratio < 0:
        errors.append("[core] drift_critical_threshold_ratio must be >= 0")

    if core.drift_warning_threshold_ratio > core.drift_critical_threshold_ratio:
        errors.append(
            "[core] drift_warning_threshold_ratio must be <= drift_critical_threshold_ratio"
        )

    if core.drift_min_events_for_evaluation <= 0:
        errors.append("[core] drift_min_events_for_evaluation must be > 0")

    if core.delta_loop_resync_threshold <= 0:
        errors.append("[core] delta_loop_resync_threshold must be > 0")

    if core.delta_breaker_ghost_threshold <= 0:
        errors.append("[core] delta_breaker_ghost_threshold must be > 0")

    if core.delta_breaker_stale_page_threshold <= 0:
        errors.append("[core] delta_breaker_stale_page_threshold must be > 0")

    if core.delta_breaker_cooldown_seconds <= 0:
        errors.append("[core] delta_breaker_cooldown_seconds must be > 0")

    if "{original}" not in core.storage_template and "{sha8}" not in core.storage_template:
        errors.append("[core] storage_template must include at least {original} or {sha8}")


def _validate_accounts(accounts: list[AccountConfig], errors: list[str]) -> None:
    """Validate account sections and uniqueness constraints."""

    if not accounts:
        errors.append("At least one [account.<name>] section is required")
        return

    if not any(account.enabled for account in accounts):
        errors.append("At least one account must be enabled")

    token_cache_paths: set[Path] = set()
    delta_cursor_paths: set[Path] = set()
    names_seen: set[str] = set()

    for account in accounts:
        if not ACCOUNT_NAME_PATTERN.fullmatch(account.name):
            errors.append(
                "Account name must match ^[a-z0-9_-]+$: "
                f"{account.name}"
            )

        if account.name in names_seen:
            errors.append(f"Duplicate account section name: {account.name}")
        names_seen.add(account.name)

        if account.provider != SUPPORTED_PROVIDER:
            errors.append(
                f"[account.{account.name}] provider must be '{SUPPORTED_PROVIDER}'"
            )

        if account.token_cache in token_cache_paths:
            errors.append(
                f"Duplicate token_cache path across accounts: {account.token_cache}"
            )
        token_cache_paths.add(account.token_cache)

        if account.delta_cursor in delta_cursor_paths:
            errors.append(
                f"Duplicate delta_cursor path across accounts: {account.delta_cursor}"
            )
        delta_cursor_paths.add(account.delta_cursor)

        if account.max_downloads is not None and account.max_downloads <= 0:
            errors.append(
                f"[account.{account.name}] max_downloads must be > 0 when set"
            )


def _get_str(
    section: configparser.SectionProxy,
    key: str,
    errors: list[str],
    *,
    required: bool = False,
    default: str | None = None,
) -> str:
    """Read a string key with optional required/default behavior."""

    raw = section.get(key, fallback=None)
    if raw is None:
        if required:
            errors.append(f"[{section.name}] missing required key: {key}")
            return ""
        return "" if default is None else default
    value = raw.strip()
    if required and not value:
        errors.append(f"[{section.name}] key must not be empty: {key}")
    return value


def _get_path(
    section: configparser.SectionProxy,
    key: str,
    errors: list[str],
    *,
    required: bool = False,
    default: str | None = None,
) -> Path:
    """Read a path value and convert it to Path."""

    value = _get_str(section, key, errors, required=required, default=default)
    return Path(value) if value else Path(".")


def _get_int(
    section: configparser.SectionProxy,
    key: str,
    errors: list[str],
    *,
    required: bool = False,
    default: int | None = None,
) -> int:
    """Read an integer key and record errors on invalid values."""

    raw = section.get(key, fallback=None)
    if raw is None:
        if required:
            errors.append(f"[{section.name}] missing required key: {key}")
            return 0
        return 0 if default is None else default
    try:
        return int(raw.strip())
    except ValueError:
        errors.append(f"[{section.name}] key must be integer: {key}")
        return 0 if default is None else default


def _get_float(
    section: configparser.SectionProxy,
    key: str,
    errors: list[str],
    *,
    required: bool = False,
    default: float | None = None,
) -> float:
    """Read a float key and record errors on invalid values."""

    raw = section.get(key, fallback=None)
    if raw is None:
        if required:
            errors.append(f"[{section.name}] missing required key: {key}")
            return 0.0
        return 0.0 if default is None else default
    try:
        return float(raw.strip())
    except ValueError:
        errors.append(f"[{section.name}] key must be float: {key}")
        return 0.0 if default is None else default


def _get_optional_int(
    section: configparser.SectionProxy,
    key: str,
    errors: list[str],
    *,
    default: int,
) -> int | None:
    """Read an optional integer that inherits from core when missing."""

    raw = section.get(key, fallback=None)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        errors.append(f"[{section.name}] key must be integer: {key}")
        return default


def _get_bool(
    section: configparser.SectionProxy,
    key: str,
    errors: list[str],
    *,
    required: bool = False,
    default: bool | None = None,
) -> bool:
    """Read a boolean value supporting configparser boolean literals."""

    raw = section.get(key, fallback=None)
    if raw is None:
        if required:
            errors.append(f"[{section.name}] missing required key: {key}")
            return False
        return False if default is None else default

    value = raw.strip().lower()
    truthy = {"1", "yes", "true", "on"}
    falsy = {"0", "no", "false", "off"}
    if value in truthy:
        return True
    if value in falsy:
        return False

    errors.append(f"[{section.name}] key must be boolean: {key}")
    return False if default is None else default
