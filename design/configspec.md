# photo-ingress Configuration Specification
This document defines the structure, required fields, defaults, and validation rules for the central configuration file used by the photo-ingress service.

Format: INI
Location: /etc/nightfall/photo-ingress.conf (recommended)

---

## 0. Naming Matrix (Canonical V1)

| Scope | Canonical Name | Notes |
|---|---|---|
| Project and service | `photo-ingress` | Primary operational name |
| Source adapter | `onedrive` | Current source adapter |
| Config file | `/etc/nightfall/photo-ingress.conf` | Central versioned INI file |
| SSD dataset | `ssdpool/photo-ingress` | Working set and state |
| SSD mountpoint | `/mnt/ssd/photo-ingress` | Staging, registry, token cache, cursors |
| HDD dataset | `nightfall/media/photo-ingress` | Ingress queue and trash boundary |
| HDD mountpoint | `/nightfall/media/photo-ingress` | `accepted/` and `trash/` |
| Permanent library | `/nightfall/media/pictures` | Read-only from ingress perspective |
| Status file | `/run/nightfall-status.d/photo-ingress.json` | Health state export path |

Naming policy:
- Use `photo-ingress` for all service-level naming.
- Keep `onedrive` explicit for adapter/account fields and module paths.

---

## 1. Global Structure

The configuration file consists of:
- A `[core]` section for global settings.
- One `[account.<name>]` section per OneDrive account.
- Optional `[logging]` section for local format overrides.

Example structure:

```ini
[core]
config_version = 1
poll_interval_minutes = 720
process_accounts_in_config_order = true
staging_path = /mnt/ssd/photo-ingress/staging
accepted_path = /nightfall/media/photo-ingress/accepted
trash_path = /nightfall/media/photo-ingress/trash
registry_path = /mnt/ssd/photo-ingress/registry.db
staging_on_same_pool = false
storage_template = {yyyy}/{mm}/{original}
verify_sha256_on_first_download = true
max_downloads_per_poll = 200
max_poll_runtime_seconds = 300
live_photo_capture_tolerance_seconds = 3
live_photo_stem_mode = exact_stem
live_photo_component_order = photo_first
live_photo_conflict_policy = nearest_capture_time
sync_hash_import_enabled = true
sync_hash_import_path = /nightfall/media/pictures
sync_hash_import_glob = .hashes.sha1

[account.christopher]
enabled = true
display_name = Christopher iPhone
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = REPLACE_WITH_CLIENT_ID
onedrive_root = /Camera Roll
token_cache = /mnt/ssd/photo-ingress/tokens/christopher.json
delta_cursor = /mnt/ssd/photo-ingress/cursors/christopher.cursor

[account.danny]
enabled = false
display_name = Danny iPhone
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = REPLACE_WITH_CLIENT_ID
onedrive_root = /Camera Roll
token_cache = /mnt/ssd/photo-ingress/tokens/danny.json
delta_cursor = /mnt/ssd/photo-ingress/cursors/danny.cursor

[logging]
log_level = INFO
console_format = json
```

---

## 2. [core] Section

### Required Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `config_version` | int | 1 | Config schema version. Must match supported value. |
| `poll_interval_minutes` | int | 720 | Poll interval used by timer cadence. Production recommendation: 8-24h (`480-1440`). |
| `staging_path` | path | none | SSD-backed staging directory. |
| `accepted_path` | path | none | Ingress-visible accepted queue. Operator later moves files manually to permanent library. |
| `trash_path` | path | none | Directory watched by systemd .path unit for reject workflow. |
| `registry_path` | path | none | SQLite registry file path. |
| `staging_on_same_pool` | bool | false | Enables rename move optimization when true. |
| `storage_template` | string | `{yyyy}/{mm}/{original}` | Template for accepted queue file layout. |
| `process_accounts_in_config_order` | bool | true | Process enabled accounts serially in the order they appear in the config file. |
| `verify_sha256_on_first_download` | bool | true | If advisory SHA1 prefilter indicates a match, still force one first-download SHA-256 verification before trusting skip behavior. |

### Optional Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_downloads_per_poll` | int | 200 | Backpressure control per poll run. |
| `max_poll_runtime_seconds` | int | 300 | Runtime cap for a single poll run. |
| `tmp_ttl_minutes` | int | 120 | Cleanup TTL for incomplete `.tmp` files. |
| `failed_ttl_hours` | int | 24 | Cleanup TTL for failed artifacts. |
| `orphan_ttl_days` | int | 7 | Cleanup TTL for orphaned staged files. |
| `live_photo_capture_tolerance_seconds` | int | 3 | Maximum capture-time delta for correlating Live Photo components. |
| `live_photo_stem_mode` | string | `exact_stem` | Filename stem comparison mode for pair detection (`exact_stem` in V1). |
| `live_photo_component_order` | string | `photo_first` | Preferred logical ordering of pair members (`photo_first` in V1). |
| `live_photo_conflict_policy` | string | `nearest_capture_time` | Rule to resolve candidate conflicts when multiple pair matches are possible. |
| `sync_hash_import_enabled` | bool | true | Enable hash import sync mode from permanent library. |
| `sync_hash_import_path` | path | none | Read-only permanent library root (for hash import mode). |
| `sync_hash_import_glob` | string | `.hashes.sha1` | Hash cache file pattern to reuse from immich-rmdups flow. |

---

## 3. [account.<name>] Sections

Each account section defines one OneDrive personal account.

### Required Keys

| Key | Type | Description |
|-----|------|-------------|
| `enabled` | bool | Whether this account is active. |
| `provider` | string | Source adapter identifier. V1 must be `onedrive`. |
| `authority` | string | Microsoft identity authority, default should be consumers endpoint. |
| `client_id` | string | Azure app registration client ID. |
| `onedrive_root` | path | Root folder to poll (for example `/Camera Roll`). |
| `token_cache` | path | Path to MSAL token cache file. |
| `delta_cursor` | path | Path to delta cursor file. |

### Optional Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `display_name` | string | section name | Human-readable account label for logs. |
| `max_downloads` | int | inherits from core | Per-account download cap override. |

---

## 4. Template Variables

The storage template supports the following variables:

| Variable | Description |
|----------|-------------|
| `{yyyy}` | Year (UTC) |
| `{mm}` | Month (UTC, zero-padded) |
| `{dd}` | Day (UTC, zero-padded) |
| `{sha256}` | Full SHA-256 hash |
| `{sha8}` | First 8 characters of SHA-256 |
| `{original}` | Original filename from OneDrive (sanitized) |
| `{account}` | Account name |

---

## 5. Validation Rules

- `config_version` must match the implementation-supported version.
- At least one account must be enabled.
- When `process_accounts_in_config_order=true`, enabled accounts are processed serially in declaration order from the INI file.
- Account names must be unique and match `^[a-z0-9_-]+$`.
- All configured directories must exist or be creatable.
- Mount roots must exist before startup (fail fast if missing).
- `token_cache` files must be mode 0600 and parent directory mode 0700.
- `delta_cursor` paths must be writable.
- `storage_template` must include at least `{original}` or `{sha8}`.
- `sync_hash_import_path` must be readable when sync import is enabled.
- `token_cache` and `delta_cursor` paths must not be reused by multiple accounts.
- `live_photo_stem_mode`, `live_photo_component_order`, and `live_photo_conflict_policy` must be validated against allowed enumerations.

---

## 6. Operational Notes

- `accepted_path` is not the permanent archive. It is the ingress queue destination.
- The operator periodically moves accepted files into `/nightfall/media/pictures/...` manually, outside ingress visibility.
- The registry remains the source of truth for prior acceptance. Files moved out of `accepted_path` must still remain blocked from re-download.
- In sync mode, the CLI imports hashes from permanent library hash caches (`.hashes.sha1`) to pre-seed accepted records and reduce re-hashing cost.
- With `verify_sha256_on_first_download=true` (default), imported/advisory SHA1 matches are not trusted as canonical identity until one server-side SHA-256 confirmation occurs.

---

## 7. Summary

This specification defines a strict and migration-ready configuration model with multi-account support, resilient state tracking, and an explicit boundary between ingress queue storage and the permanent photo library.
