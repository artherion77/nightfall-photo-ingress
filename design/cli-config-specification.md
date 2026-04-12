# photo-ingress CLI and Configuration Specification

This document defines the CLI interface and configuration schema for the
`nightfall-photo-ingress` executable. It is the authoritative reference for all
CLI commands, global options, configuration file structure, defaults, and validation
rules.

Status: active
Date: 2026-04-02
Updated: 2026-04-12
Author: Systems Engineering
Issue: #65 (hash-import command and invariants)

---

# Part 1 — CLI Specification

## 1. Executable

```
/opt/ingress/bin/nightfall-photo-ingress
```

### 1.1 Global Syntax

```
nightfall-photo-ingress [GLOBAL OPTIONS] <command> [COMMAND OPTIONS]
```

### 1.2 Global Options

| Option | Default | Description |
|--------|---------|-------------|
| `--log-mode {json,human}` | `human` | Override logging format |
| `--version` | — | Print version and exit |
| `--debug-httpx-transport` | off | Write redacted HTTP transport diagnostics |

---

## 2. Command Reference

### 2.1 Available Commands

```
auth-setup
discover-paths
poll
reject
accept
purge
process-trash
config-check
prune-auth-failures
hash-import              (NEW — Issue #65)
sync-import              (DEPRECATED — replaced by hash-import)
```

### 2.2 Command Summary

| Command | Description | Category |
|---------|-------------|----------|
| `auth-setup` | Initialize account authentication (MSAL device-code flow) | Auth |
| `discover-paths` | Auto-discover OneDrive storage paths using cached token | Auth |
| `poll` | Run one poll cycle (delta poll, download, ingest) | Ingest |
| `reject` | Reject a hash permanently | Lifecycle |
| `accept` | Accept a pending hash | Lifecycle |
| `purge` | Purge a rejected hash from disk | Lifecycle |
| `process-trash` | Process trash directory (filesystem-triggered rejection) | Lifecycle |
| `config-check` | Validate configuration file | Diagnostics |
| `prune-auth-failures` | Create backup and prune historical auth_failure audit rows | Maintenance |
| `hash-import` | Import SHA-256 hashes from `.hashes.v2` files into the dedupe index | Offline import |
| `sync-import` | *(deprecated)* Import advisory SHA-1 hashes from `.hashes.sha1` files | Legacy |

---

### 2.3 Per-Command Options

All commands accept `--path` (config file path, default
`/etc/nightfall/photo-ingress.conf`). This is omitted from the individual tables
for brevity but is present on every subcommand.

### auth-setup

| Option | Default | Description |
|--------|---------|-------------|
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |
| `--account <name>` | none | Named account to set up. Required when more than one enabled account exists. |
| `--verbose` | off | Show detailed Graph API calls and debug info. |
| `--skip-discovery` | off | Skip OneDrive path auto-discovery after successful authentication. |

### discover-paths

| Option | Default | Description |
|--------|---------|-------------|
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |
| `--account <name>` | none | Named account. Required when more than one enabled account exists. |
| `--verbose` | off | Show detailed Graph API calls and resolution info. |

### poll

| Option | Default | Description |
|--------|---------|-------------|
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |
| `--account <name>` | none | Named account to poll. If omitted, all enabled accounts are polled in config declaration order. |
| `--verbose` | off | Show detailed Graph API calls and progress trace info. |

### reject

| Option | Default | Description |
|--------|---------|-------------|
| `<sha256>` | — | SHA-256 hash of the file to reject (positional). |
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |
| `--reason <text>` | none | Optional audit note recorded with the rejection. |

### accept

| Option | Default | Description |
|--------|---------|-------------|
| `<sha256>` | — | SHA-256 hash of the file to accept (positional). |
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |
| `--reason <text>` | none | Optional audit note recorded with the acceptance. |

### purge

| Option | Default | Description |
|--------|---------|-------------|
| `<sha256>` | — | SHA-256 hash of the file to purge (positional). |
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |
| `--reason <text>` | none | Optional audit note recorded with the purge. |

### process-trash

| Option | Default | Description |
|--------|---------|-------------|
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |

### config-check

| Option | Default | Description |
|--------|---------|-------------|
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |

### prune-auth-failures

| Option | Default | Description |
|--------|---------|-------------|
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |
| `--backup-path <file>` | auto (registry name + UTC timestamp + `.bak`) | Explicit backup destination for the registry database before pruning. |
| `--keep-latest <N>` | `0` | Keep the latest N `auth_failure` audit rows instead of pruning all. |

### sync-import (deprecated)

| Option | Default | Description |
|--------|---------|-------------|
| `--path <file>` | `/etc/nightfall/photo-ingress.conf` | Config file path. |
| `--dry-run` | off | Show what would be imported without writing to the registry. |

---

## 3. New Command: `hash-import` (Issue #65)

The `hash-import` command imports SHA-256 hashes from `.hashes.v2` cache files into the
registry dedupe index without triggering ingest, audit, or UI-visible state changes.

`hash-import` is not an ingest event, does not create staging items, does not generate
audit events, and is not visible in any UI surface.

### 3.1 Syntax

```
nightfall-photo-ingress hash-import <path-to-root> [OPTIONS]
```

Where `<path-to-root>` is the root directory of a library tree containing `.hashes.v2`
files generated by `nightfall-immich-rmdups.sh`. The command recursively discovers all
`.hashes.v2` files under the root and imports valid SHA-256 entries.

### 3.2 Purpose

- Pre-seed the registry with known SHA-256 hashes from an external library
- Prevent re-downloads of content already present in the permanent library
- Support legacy library onboarding to the dedupe index
- Populate the dedupe index without ingesting files or triggering any pipeline behavior

### 3.3 Command Options

| Option | Default | Description |
|--------|---------|-------------|
| `--chunk-size <N>` | `1000` | Number of hashes per import batch (config override) |
| `--dry-run` | off | Validate files and show stats without importing |
| `--quiet` | off | Suppress non-error output |
| `--stats` | off | Show per-chunk statistics |
| `--stop-on-error` | off | Abort on first invalid hash |

### 3.4 Hash Import Input Format

The `hash-import` command consumes `.hashes.v2` files produced by
`nightfall-immich-rmdups.sh`. The previous `.hashes.sha1` format is not accepted.

#### 3.4.1 `.hashes.v2` File Structure

A valid `.hashes.v2` file has:

- Line 1: cache schema marker
  ```
  CACHE_SCHEMA v2
  ```
- Line 2: directory hash line
  ```
  DIRECTORY_HASH <40-char-sha1-of-directory-listing>
  ```
- Lines 3..N: tab-separated rows
  ```
  <sha1>\t<sha256>\t<absolute-path>
  ```

Where:
- `<sha1>` is the SHA-1 of the file contents (present for tooling compatibility)
- `<sha256>` is the SHA-256 of the file contents (used as canonical identity)
- `<absolute-path>` is the full path to the file in the external library

#### 3.4.2 Validation Rules

The hash import logic MUST:

1. Verify that the first line is exactly `CACHE_SCHEMA v2`.
2. Verify that the second line matches `DIRECTORY_HASH <40-hex>`.
3. Verify that each subsequent line:
   - contains at least 3 tab-separated fields
   - has a valid 40-char hex SHA-1 in column 1
   - has a valid 64-char hex SHA-256 in column 2
   - has a non-empty path in column 3

If any of these checks fail, the `.hashes.v2` file MUST be treated as invalid and
skipped with a logged warning.

#### 3.4.3 Directory Hash Semantics

The `DIRECTORY_HASH` line encodes a deterministic hash of the directory listing
(filenames, sizes, mtimes). If `DIRECTORY_HASH` does not match the current directory
listing hash, the `.hashes.v2` file MUST be considered stale and MUST NOT be trusted.
Stale `.hashes.v2` files MUST be recomputed before their contents are used for import.

There is no "best effort" mode: partially valid `.hashes.v2` files MUST NOT be consumed.

#### 3.4.4 Import Column Usage

- Only the SHA-256 column (column 2) is used to populate the registry dedupe index.
- The path column (column 3) is not imported into the registry and MUST NOT be used
  to infer account ownership or ingest state.
- The SHA-1 column (column 1) is present for compatibility with existing tooling but
  MUST NOT be used as canonical identity in photo-ingress.

### 3.5 Output Format

#### Standard Mode

```
[chunk 1] imported=998 skipped_existing=2 duration=0.12s
[chunk 2] imported=1000 skipped_existing=0 duration=0.11s
DONE: total_imported=1998 total_skipped=2
```

#### Dry Run

```
DRY RUN: total=2000 new=1998 existing=2
```

#### Quiet Mode

Only errors are printed.

### 3.6 Error Handling

| Error | Example |
|-------|---------|
| Invalid hash | `ERROR: invalid hash on line 42` |
| File not found | `ERROR: cannot open file` |
| Permission denied | `ERROR: insufficient permissions` |
| Registry locked | `ERROR: registry is locked` |
| Stop on error | Import aborts immediately |
| Stale directory hash | `WARNING: stale .hashes.v2 in <dir>, recomputing` |

### 3.7 Idempotency Rules

The `hash-import` operation MUST be:

- Duplicate-tolerant: importing the same hash again produces no error and no state change
- Order-independent: results are identical regardless of import order
- Repeatable without side effects: re-running the command yields the same end state
- Safe under partial overlap: overlapping `.hashes.v2` files are handled gracefully
- Race-free: registry locking is enforced during writes

Behavior:
- Duplicate hashes are silently skipped
- Existing registry entries are silently skipped (never overwritten)
- Re-importing the same file produces no errors

### 3.8 Hash-Import Invariants (Mandatory)

The following 12 invariants are strictly enforced. In case of conflict, these rules
take precedence over any other existing design statements.

1. Imported hashes MUST NOT create staging items.
2. Imported hashes MUST NOT create audit events of any kind.
3. Imported hashes MUST NOT enter or modify the ingest lifecycle (pending/accepted/rejected).
4. Imported hashes MUST NOT participate in live-photo-pair detection.
5. Imported hashes MUST NOT trigger thumbnail generation or any media pipeline.
6. Imported hashes MUST be fully idempotent (duplicates, overlaps, re-imports MUST NOT cause errors or state changes).
7. Imported hashes MUST NOT overwrite or mutate existing registry entries.
8. Imported hashes MUST NOT modify or influence the OneDrive delta token or ingest cursor.
9. Imported hashes MUST NOT appear in any UI surfaces that represent ingest state (Dashboard, Staging, Audit Preview).
10. Imported hashes MUST NOT infer or assign account ownership (account MUST remain null).
11. Imported hashes MUST NOT participate in EXIF-based heuristics (timestamps, orientation, pairing, clustering).
12. Imported hashes MUST NOT be eligible for reject/purge operations or any file-based lifecycle actions.

### 3.9 Registry Semantics

A successful `hash-import` creates or confirms a registry entry with the following
shape:

```json
{
  "sha256": "<hash>",
  "imported": true,
  "first_seen": "<timestamp>",
  "source": "hash_import"
}
```

No additional fields are added. Imported entries are used solely for dedupe index
lookups during ingest pre-download filtering. They do not participate in the
`files.status` state machine and carry no lifecycle semantics.

### 3.10 Operational Notes

- Import is offline (no network access required)
- Import is not reversible (imported hashes remain in the dedupe index)
- Import is not UI-visible (no dashboard, staging, or audit surface)
- Import only affects dedupe behavior (prevents re-downloads)
- Import does not affect ingest, audit, or delta-token state
- Import does not assign accounts
- Import does not rely on EXIF data

---

## 4. Deprecated Command: `sync-import`

The `sync-import` command is legacy and is replaced by `hash-import` (Issue #65).

`sync-import` imported advisory SHA-1 hashes from `.hashes.sha1` files into the
`external_hash_cache` table. This approach is superseded because:

- SHA-1 is not a canonical identity (INV-R01: SHA-256 is the canonical content identity)
- Advisory hashes required a first-download SHA-256 verification before they could
  gate future skips, negating most of the download-reduction benefit
- The `hash-import` command imports authoritative SHA-256 hashes directly, eliminating
  the advisory layer entirely

The `sync-import` command remains available in the current runtime for backward
compatibility but is scheduled for removal. New deployments MUST use `hash-import`.

---

# Part 2 — Configuration Specification

Format: INI
Location: /etc/nightfall/photo-ingress.conf (recommended)

## 5. Naming Matrix (Canonical V2)

| Scope | Canonical Name | Notes |
|---|---|---|
| Project and service | `photo-ingress` | Primary operational name |
| Source adapter | `onedrive` | Current source adapter |
| Config file | `/etc/nightfall/photo-ingress.conf` | Central versioned INI file |
| SSD dataset | `ssdpool/photo-ingress` | Working set and state |
| SSD mountpoint | `/mnt/ssd/photo-ingress` | Staging, registry, token cache, cursors |
| HDD dataset | `nightfall/media/photo-ingress` | Ingress queue and trash boundary |
| HDD mountpoint | `/nightfall/media/photo-ingress` | `pending/`, `accepted/`, `rejected/`, and `trash/` |
| Permanent library | `/nightfall/media/pictures` | Read-only from ingress perspective |
| Status file | `/run/nightfall-status.d/photo-ingress.json` | Health state export path |

Naming policy:
- Use `photo-ingress` for all service-level naming.
- Keep `onedrive` explicit for adapter/account fields and module paths.

---

## 6. Global Structure

The configuration file consists of:
+ A `[core]` section for global settings.
+ One `[account.<name>]` section per OneDrive account.
+ An optional `[import]` section for hash-import defaults (planned — see §8).
+ An optional `[logging]` section for local format overrides.
+ An optional `[web]` section for the embedded API server.

Example structure:

```ini
[core]
config_version = 2
poll_interval_minutes = 720
process_accounts_in_config_order = true
staging_path = /mnt/ssd/photo-ingress/staging
pending_path = /nightfall/media/photo-ingress/pending
accepted_path = /nightfall/media/photo-ingress/accepted
accepted_storage_template = {yyyy}/{mm}/{original}
rejected_path = /nightfall/media/photo-ingress/rejected
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

[import]
chunk_size = 1000

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

## 7. [core] Section

### 7.1 Required Keys

The following keys have no parser default and cause config validation to fail if
omitted.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `config_version` | int | 2 | Config schema version. Must match supported value. |
| `staging_path` | path | none | SSD-backed staging directory. |
| `pending_path` | path | none | Ingest-visible pending queue for newly discovered files. |
| `accepted_path` | path | none | Operator-accepted destination path. |
| `rejected_path` | path | none | Rejected retention folder (trash-like) until purge. |
| `trash_path` | path | none | Directory watched by systemd .path unit for reject workflow. |
| `registry_path` | path | none | SQLite registry file path. |

### 7.2 Optional Keys

The following keys have parser defaults and may be omitted from the config file.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `poll_interval_minutes` | int | `15` | Poll interval. Production recommendation: 480–1440 (8–24h). Code default is 15 (development-friendly). |
| `accepted_storage_template` | string | `{yyyy}/{mm}/{original}` | Template for accepted destination layout. |
| `staging_on_same_pool` | bool | `false` | Enables rename-based move optimization when staging and pending are on the same ZFS pool. |
| `storage_template` | string | `{yyyy}/{mm}/{original}` | Template for pending queue file layout. |
| `process_accounts_in_config_order` | bool | `true` | Process enabled accounts serially in config declaration order. When false, sorted by account name. |
| `verify_sha256_on_first_download` | bool | `true` | Require server-side SHA-256 verification before trusting metadata-only skip for advisory prefilter matches. |
| `max_downloads_per_poll` | int | 200 | Backpressure control per poll run. |
| `max_poll_runtime_seconds` | int | 300 | Runtime cap for a single poll run. |
| `tmp_ttl_minutes` | int | `120` | Cleanup TTL for incomplete `.tmp` staging files. |
| `failed_ttl_hours` | int | `24` | Cleanup TTL for failed staging artifacts. |
| `orphan_ttl_days` | int | `7` | Cleanup TTL for orphaned staged files. |
| `thumbnail_cache_path` | path | `{staging_path.parent}/cache/thumbnails` | Directory for lazily generated thumbnail files used by the API server. |
| `live_photo_capture_tolerance_seconds` | int | 3 | Maximum capture-time delta for correlating Live Photo components. |
| `live_photo_stem_mode` | string | `exact_stem` | Filename stem comparison mode for pair detection (`exact_stem` in V1). |
| `live_photo_component_order` | string | `photo_first` | Preferred logical ordering of pair members (`photo_first` in V1). |
| `live_photo_conflict_policy` | string | `nearest_capture_time` | Rule to resolve candidate conflicts when multiple pair matches are possible. |

### 7.3 Advanced Operational Keys

These keys tune runtime safety, circuit-breaker, and backpressure behavior. Defaults are
safe for production. Override only when guided by observability data.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `integrity_mode` | string | `strict` | Ingest integrity policy. Enum: `strict`, `tolerant`. |
| `drift_warning_threshold_ratio` | float | `0.05` | Ratio of unexpected registry events that triggers a drift warning log. |
| `drift_critical_threshold_ratio` | float | `0.20` | Ratio that triggers a critical drift alert. Must be ≥ `drift_warning_threshold_ratio`. |
| `drift_min_events_for_evaluation` | int | `20` | Minimum event count before drift ratios are evaluated. |
| `drift_fail_fast_enabled` | bool | `true` | Abort the poll cycle when the critical drift threshold is reached. |
| `delta_loop_resync_threshold` | int | `3` | Consecutive delta pages with no new items before forcing a full delta resync. |
| `delta_breaker_ghost_threshold` | int | `10` | Consecutive ghost-item responses before the delta circuit breaker trips. |
| `delta_breaker_stale_page_threshold` | int | `10` | Consecutive stale pages before the circuit breaker trips. |
| `delta_breaker_cooldown_seconds` | int | `300` | Cooldown after circuit breaker trips before poll resumes. |
| `account_worker_count` | int | `1` | Concurrent account poll workers. V1 value is 1. |
| `adaptive_backpressure_enabled` | bool | `true` | Enable adaptive backpressure when download queues grow. |
| `backpressure_retry_threshold` | int | `20` | Consecutive retry errors before backpressure activates. |
| `backpressure_transport_error_threshold` | int | `5` | Consecutive transport errors before backpressure activates. |
| `backpressure_cooldown_seconds` | int | `300` | Cooldown period after backpressure activation. |

### 7.4 Deprecated Keys (Legacy — scheduled for removal)

| Key | Type | Default | Replacement |
|-----|------|---------|-------------|
| `sync_hash_import_enabled` | bool | true | Use `hash-import` CLI command instead |
| `sync_hash_import_path` | path | none | Pass `<path-to-root>` as argument to `hash-import`. **Parser-required until H7 is implemented — see note below.** |
| `sync_hash_import_glob` | string | `.hashes.sha1` | `hash-import` reads `.hashes.v2` files only |

These keys are recognized by the current runtime for backward compatibility with
`sync-import` but are not used by `hash-import` and will be removed in a future release.

**Operational hazard:** `sync_hash_import_path` is currently parser-required (no default).
Omitting it causes config validation to fail with "missing required key: sync_hash_import_path"
even though the feature is deprecated. Keep a placeholder value until the H7 implementation
chunk removes the parser requirement.

---

## 8. [import] Section (NEW — Issue #65)

The `[import]` section provides defaults for the `hash-import` command.

> **Implementation status:** This section is specified for Issue #65 (implementation
> chunk H7). The current config validator rejects `[import]` with
> "Unsupported section [import] for v2 config model". Do not add `[import]` to
> production config files until H7 is implemented.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `chunk_size` | int | `1000` | Number of hashes per import batch. CLI `--chunk-size` overrides this value. |

Precedence rules:
1. CLI option (`--chunk-size`) overrides config value.
2. Config value overrides internal default.
3. Tests may set small chunk sizes (e.g., 10).
4. `chunk_size` MUST be > 0.

---

## [logging] Section

Optional. Overrides logging format for the process. Omitting the section applies defaults.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `log_level` | string | `INFO` | Log level. One of `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `console_format` | string | `json` | Log line format. One of `json`, `human`. |

The global `--log-mode` CLI option overrides `console_format` at runtime.

---

## [web] Section

Optional. Configures the embedded API server. Omitting the section is safe for
CLI-only deployments; all keys default to safe localhost-bound values.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `api_token` | string | (empty) | Static bearer token for API request authentication. Empty string disables token auth. |
| `bind_host` | string | `127.0.0.1` | Bind address for the API server. Default is localhost-only. |
| `bind_port` | int | `8000` | TCP port for the API server. |
| `cors_allowed_origins` | string | `http://localhost:8000` | Comma-separated list of allowed CORS origins. |

---

## 9. [account.<name>] Sections

Each account section defines one OneDrive personal account.

### Required Keys

| Key | Type | Description |
|-----|------|-------------|
| `provider` | string | Source adapter identifier. Must be `onedrive`. |
| `client_id` | string | Azure app registration client ID. |
| `onedrive_root` | path | Root folder to poll (for example `/Camera Roll`). |
| `token_cache` | path | Path to MSAL token cache file. |
| `delta_cursor` | path | Path to delta cursor file. |

### Optional Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Whether this account is active. |
| `authority` | string | `https://login.microsoftonline.com/consumers` | Microsoft identity authority URL. Override for work/school tenants with tenant ID. |
| `display_name` | string | section name | Human-readable account label for logs. |
| `max_downloads` | int | inherits from core | Per-account download cap override. |

---

## 10. Template Variables

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

## 11. Validation Rules

- `config_version` must be `2`.
- `pending_path`, `accepted_path`, `rejected_path`, and `trash_path` are all required and must be distinct.
- At least one account must be enabled.
- When `process_accounts_in_config_order=true`, enabled accounts are processed serially in declaration order from the INI file.
- Account names must be unique and match `^[a-z0-9_-]+$`.
- All configured directories must exist or be creatable.
- Mount roots must exist before startup (fail fast if missing).
- `token_cache` files must be mode 0600 and parent directory mode 0700.
- `delta_cursor` paths must be writable.
- `storage_template` must include at least `{original}` or `{sha8}`.
- `accepted_storage_template` must include at least `{original}` or `{sha8}`.
- `token_cache` and `delta_cursor` paths must not be reused by multiple accounts.
- `live_photo_stem_mode`, `live_photo_component_order`, and `live_photo_conflict_policy` must be validated against allowed enumerations.
- `[import] chunk_size` must be a positive integer if present. **Note: the `[import]` section is not yet accepted by the config validator (H7); adding it fails validation until implemented.**
- `integrity_mode` must be one of `strict`, `tolerant`.
- `drift_warning_threshold_ratio` must be ≥ 0 and ≤ `drift_critical_threshold_ratio`.
- `drift_min_events_for_evaluation` must be > 0.
- Delta breaker threshold and cooldown values must be > 0.
- Backpressure threshold and cooldown values must be > 0.
- `account_worker_count` must be > 0.
- `poll_interval_minutes` must be > 0. The code default is 15 (dev-friendly); production deployments should set 480–1440.
- Unsupported section names (anything other than `core`, `logging`, `web`, `account.*`) cause a validation error.

---

## 12. Operational Notes

- `pending_path` is the automatic ingest destination. New files land in `pending` first.
- Operators explicitly move files from `pending` to `accepted` with the `accept` command.
- Rejected files are moved into `rejected_path` and retained until `purge` or manual deletion.
- The registry remains the source of truth for prior acceptance/rejection. Files moved out of queue paths remain blocked from re-download.
- `hash-import` seeds the dedupe index from `.hashes.v2` files in the permanent library. Imported hashes prevent future re-downloads of known content. The import is offline, non-audit, and not UI-visible.
- The permanent library (`/nightfall/media/pictures`) is read-only to the ingress service. Neither `hash-import` nor any other command writes to the permanent library.

---

## 13. Config Integration for hash-import

The `hash-import` command reads the configuration file to resolve `registry_path`
(the SQLite database to insert hashes into) and the `[import]` section for
`chunk_size` defaults.

The command does not read or use the deprecated `sync_hash_import_*` keys from
`[core]`. Those keys are consumed only by the legacy `sync-import` command.

Operator workflow:

```bash
# Typical hash-import invocation
nightfall-photo-ingress hash-import /nightfall/media/pictures \
  --path /etc/nightfall/photo-ingress.conf \
  --stats

# Dry-run preview
nightfall-photo-ingress hash-import /nightfall/media/pictures \
  --path /etc/nightfall/photo-ingress.conf \
  --dry-run

# Override chunk size from CLI
nightfall-photo-ingress hash-import /nightfall/media/pictures \
  --path /etc/nightfall/photo-ingress.conf \
  --chunk-size 500 --stats
```

---

## 14. Summary

This specification defines the v2.0 CLI and configuration model with strict
queue-boundary separation, explicit operator transitions, no accepted-first
compatibility fallbacks, and the new `hash-import` command for offline dedupe
index seeding (Issue #65).
