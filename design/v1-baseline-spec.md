# photo-ingress V1 Baseline Specification

Status: accepted baseline
Date: 2026-03-31

---

## 1. V1 Scope and Non-Goals

### In Scope
- Python service running in the `photo-ingress` LXC container with systemd-managed execution.
- OneDrive ingest for one or more personal Microsoft accounts.
- Polling via Microsoft Graph delta API.
- SSD staging download area and authoritative global SQLite registry.
- Accepted queue in `/nightfall/media/photo-ingress/accepted`.
- Reject flow via trash watcher and CLI reject command.
- Live Photo support in V1 (pair detection and metadata linkage).
- Sync import mode from permanent library hash caches (`.hashes.sha1`).
- Structured logging and health status JSON export.

### Explicit Non-Goals for V1
- Auto-copy from accepted queue to permanent library.
- Any write access from ingress into `/nightfall/media/pictures`.
- Live Photo merge/export transformations.

---

## 2. Canonical Naming Matrix (V1)

| Scope | Canonical Name | Notes |
|---|---|---|
| Project and service | `photo-ingress` | Primary operational identifier |
| Source adapter | `onedrive` | Current adapter; adapter name remains explicit |
| CLI command | `photo-ingress` | Main operator interface |
| Config file | `/etc/nightfall/photo-ingress.conf` | Single central config |
| SSD dataset (container) | `ssdpool/photo-ingress` | Staging and state |
| SSD mountpoint | `/mnt/ssd/photo-ingress` | Registry, token, cursor, staging |
| HDD dataset (container) | `nightfall/media/photo-ingress` | Queue + trash boundary |
| HDD mountpoint | `/nightfall/media/photo-ingress` | Accepted queue and trash |
| Permanent library | `/nightfall/media/pictures` | Read-only for ingress |
| Status file | `/run/nightfall-status.d/photo-ingress.json` | Health export |

---

## 3. System Boundaries

- Source authority for new media candidates: OneDrive delta stream.
- Ingest authority for accept/reject lifecycle: photo-ingress registry.
- Immich role: viewer/indexer over permanent library only.

Important boundary:
- `accepted_path` is an ingress queue only.
- Operator manually moves files from accepted queue to `/nightfall/media/pictures/...` outside ingress visibility.
- Even after manual moves, ingress must never re-download previously accepted content because acceptance history is persisted in registry tables.

---

## 4. Storage Layout

### SSD pool (always-on logic)
- `/mnt/ssd/photo-ingress/staging/`
- `/mnt/ssd/photo-ingress/registry.db`
- `/mnt/ssd/photo-ingress/tokens/<account>.json`
- `/mnt/ssd/photo-ingress/cursors/<account>.cursor`

### HDD pool (operator boundary)
- `/nightfall/media/photo-ingress/accepted/` (ingress queue destination)
- `/nightfall/media/photo-ingress/trash/` (rejection trigger)
- `/nightfall/media/pictures/...` (permanent library, read-only to ingress)

---

## 5. Data Model (SQLite)

### 5.1 Schema versioning
- Use `PRAGMA user_version`.
- V1 target schema version: 1.
- Migrations must be transactional and idempotent.

### 5.2 Required tables

#### files
Canonical per-hash status table.
- `sha256 TEXT PRIMARY KEY`
- `size_bytes INTEGER NOT NULL`
- `status TEXT NOT NULL CHECK(status IN ('accepted','rejected','purged'))`
- `first_seen_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

#### accepted_records
Accepted history independent of current file presence.
- `sha256 TEXT PRIMARY KEY REFERENCES files(sha256)`
- `accepted_at TEXT NOT NULL`
- `original_filename TEXT`
- `storage_relpath TEXT` (path under accepted queue at accept time)
- `account_name TEXT NOT NULL`
- `onedrive_id TEXT`
- `source_modified_time TEXT`

Purpose: preserve accepted truth even when operator moves files away.

#### metadata_index
Fast pre-filter for OneDrive candidates.
- `account_name TEXT NOT NULL`
- `onedrive_id TEXT NOT NULL`
- `size_bytes INTEGER NOT NULL`
- `modified_time TEXT NOT NULL`
- `sha256 TEXT NOT NULL REFERENCES files(sha256)`
- `PRIMARY KEY (account_name, onedrive_id)`

#### live_photo_pairs
Link components for V1 Live Photo support.
- `pair_id TEXT PRIMARY KEY`
- `account_name TEXT NOT NULL`
- `capture_key TEXT NOT NULL`
- `photo_sha256 TEXT REFERENCES files(sha256)`
- `video_sha256 TEXT REFERENCES files(sha256)`
- `detection_method TEXT NOT NULL`
- `created_at TEXT NOT NULL`

#### audit_log
Append-only event stream.
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `ts TEXT NOT NULL`
- `actor TEXT NOT NULL` (`pipeline`, `trash_watch`, `cli`, `sync_import`)
- `action TEXT NOT NULL`
- `sha256 TEXT`
- `account_name TEXT`
- `details_json TEXT`

---

## 6. Configuration Contract (V1)

- Required keys and defaults are defined in `design/configspec.md`.
- At least one `account.<name>` section must be enabled.
- Account names must match `^[a-z0-9_-]+$`.
- `token_cache` and `delta_cursor` paths must be unique per account.
- Token cache file mode must be 0600 and parent directory mode 0700.

---

## 7. Pipeline Runtime Behavior

### 7.1 Poll execution model
- Triggered by systemd timer.
- One global process lock for full poll run.
- Process accounts serially in deterministic order: declaration order in config file.
- Per-account cursor and token cache are isolated.

### 7.2 Candidate decision flow
For each delta file candidate:
1. Metadata pre-filter using `(account_name, onedrive_id, size, modified_time)`.
2. If unresolved, download to staging as `.tmp` then finalize temp name.
3. Compute SHA-256.
4. Lookup in `files`:
   - `rejected`: delete staged file, audit reject duplicate.
   - `accepted`: delete staged file, audit duplicate skipped.
   - unknown: write to accepted queue, mark accepted in `files` + `accepted_records`, insert/update `metadata_index`, audit accepted.

### 7.3 Accepted queue semantics
- Write target uses configurable template, default `{yyyy}/{mm}/{original}`.
- Accepted queue is expected to be drained manually by operator.
- Registry acceptance history remains valid even if queue files disappear later.

### 7.4 Cross-pool move behavior
- If `staging_on_same_pool = true`: use atomic rename.
- Else: use copy2, verify content hash, then unlink staging file.

### 7.5 Retry and backpressure
- Max downloads and max runtime per poll from config.
- Retry HTTP errors with exponential backoff and jitter.
- Respect Graph `Retry-After` for 429/503.

### 7.6 Delta cursor fallback
On invalid/lost cursor:
1. Attempt delta recovery bootstrap.
2. Optional bounded backfill.
3. Full rescan as last resort.

Safety depends on registry idempotency.

### 7.7 Delta cursor checkpoint semantics
- During an active delta traversal, process each page in commit order: page fetch -> ingest filter/decision -> durable registry/storage writes -> cursor advance.
- Persist `@odata.nextLink` only after page side effects are committed.
- Treat cursor state as committed work progress.
- When a chain reaches `@odata.deltaLink` completion, persist `@odata.deltaLink` as the committed cursor.

---

## 8. Live Photo Support in V1

### 8.1 Requirement
Live Photo support is mandatory in V1.

### 8.2 V1 behavior
- Detect likely pairs (HEIC/JPEG + MOV) using configurable heuristics with V1 defaults:
  - `live_photo_capture_tolerance_seconds = 3`
  - `live_photo_stem_mode = exact_stem`
  - `live_photo_component_order = photo_first`
  - `live_photo_conflict_policy = nearest_capture_time`
- Ingest each component as independent file with its own hash and decision path.
- Persist pair linkage in `live_photo_pairs`.
- Do not merge or transcode components.

### 8.3 Pairing guarantees
- Pairing is best-effort and audit-visible.
- Unpaired components are still accepted/rejected independently.

---

## 9. Reject Workflows

### 9.1 Trash-driven reject
- systemd `.path` watches `/nightfall/media/photo-ingress/trash`.
- Service processes new files, hashes them, marks `rejected`, appends audit records, removes queue/trash copies if found.

### 9.2 CLI reject
- `photo-ingress reject <sha256> [--reason ...]`
- Account-agnostic and idempotent.
- If already rejected, return success with no-op audit event.

---

## 10. Sync Hash Import Mode (V1)

### 10.1 Purpose
Pre-seed accepted hashes from permanent library to avoid unnecessary OneDrive downloads.

### 10.2 Data source
- Read-only permanent library path (default `/nightfall/media/pictures`).
- Reuse `.hashes.sha1` files generated by `nightfall-immich-rmdups.sh`.
- Expected format:
  - First line: `DIRECTORY_HASH <value>`
  - Following lines: `<sha1> <filepath>` style hash rows.
- If a cache file is missing, stale, or invalid, importer re-hashes the directory contents for import only and does not rewrite any hash files in the library.

### 10.3 Import behavior
- CLI command: `photo-ingress sync-import [--path ...] [--dry-run]`
- Parse hash cache files and seed mapping rows in a dedicated table (`external_hash_cache`).
- When OneDrive metadata provides SHA1, check imported cache first:
  - If OneDrive SHA1 matches imported entry and `verify_sha256_on_first_download=false`, classify as already accepted and skip download.
  - If OneDrive SHA1 matches imported entry and `verify_sha256_on_first_download=true` (default), perform one verification download to compute server-side SHA-256 before future metadata-only skips.
  - If no match, continue normal staging + SHA-256 path.

Important:
- Imported SHA1 data is advisory for pre-filtering only.
- Canonical content identity remains server-computed SHA-256 for all newly ingested files.

---

## 11. Observability and Health

### 11.1 Logs
- JSON logs by default for service runs.
- Optional human format for interactive CLI.
- Required context keys: `account`, `action`, `status`, `sha256`, `filename`.

### 11.2 Health state machine
States:
- `healthy`
- `degraded`
- `auth_failed`
- `disk_full`
- `ingest_error`
- `registry_corrupt`

### 11.3 Status export
- Write status JSON to `/run/nightfall-status.d/photo-ingress.json` using atomic write+rename.
- Must remain compatible with nightfall-mcp health consumption.

---

## 12. Security Baseline

- No token credentials in environment variables.
- MSAL cache files stored on disk with strict modes.
- Permanent library is read-only to ingress process.
- Reject and sync-import actions are fully audit logged.

---

## 13. V1 Acceptance Criteria

- Multi-account delta polling works with per-account cursors.
- Accepted hashes persist and prevent re-download after manual file moves out of accepted queue.
- Live Photo pair metadata is persisted when detectable.
- Sync import from `.hashes.sha1` runs successfully and reduces downloads.
- Reject flow blocks future re-ingest for matching content.
- Status export and structured logs are present for every poll run.
