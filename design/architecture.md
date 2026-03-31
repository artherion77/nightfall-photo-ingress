# nightfall-photo-ingress: Architecture Design

**Status:** DRAFT — pending review  
**Date:** 2026-03-31  
**Author:** ops/copilot design session

---

## 1. Overview

A fully automated, server-side OneDrive-based photo ingest pipeline that feeds into the nightfall archival system. iOS devices upload photos to OneDrive (treated as an untrusted but reliable transport layer). A Linux server running ZFS storage ("nightfall"), Immich, and custom ingest services pulls those files down, validates them, and manages their lifecycle independently of Immich.

**Immich's role is limited to indexing and viewing permanent library content only.** The ingress service writes into an accepted queue, while the operator manually promotes files into `/nightfall/media/pictures/...` outside ingress visibility. Ingress still blocks re-downloads using persistent acceptance history in the registry.

---

## 2. High-Level Architecture

```
iOS Camera Roll
      │
      │  (automatic background upload)
      ▼
  OneDrive (personal Microsoft account)
      │
      │  Microsoft Graph API — delta poll every 15 min
      ▼
┌─────────────────────────────────────────┐
│           nightfall server              │
│                                         │
│  /mnt/ssd/onedrive-ingest/staging/      │  ← SSD; temp download area
│       │                                 │
│       │  SHA-256 hash                   │
│       │  registry lookup                │
│       ▼                                 │
│  registry.db (SQLite, SSD)              │  ← authoritative content ledger
│       │                                 │
│       ├─ rejected → delete from staging │
│       ├─ accepted → delete from staging │
│       └─ unknown  → move to accepted/   │
│                    + insert registry    │
│                                         │
│  /nightfall/media/onedrive-ingest/      │  ← HDD pool
│    accepted/   ← ingress queue           │
│    trash/      ← rejection trigger       │
└─────────────────────────────────────────┘
      │
     │  manual operator move/copy
      ▼
  /nightfall/media/pictures/... (permanent library)
     │
     │  read-only bind-mount
     ▼
  Immich (LXC container) external library
```

---

## 3. Design Constraints and Goals

- **Fully automated** — no user behavior assumptions on iOS.
- **Robust against Immich changes** — the pipeline operates independently; a fresh Immich DB simply rescans the permanent library.
- **Reject-once, reject-forever** — a rejected SHA-256 is never ingested again regardless of re-uploads.
- **Accepted-history persistence** — manually moving files out of `accepted/` must not cause future re-downloads.
- **Minimize unnecessary I/O** — metadata pre-filtering avoids downloading files that are already known; HDD only spun up at accept-commit time.
- **English-only** — all inline comments, logs, and documentation are in English.
- **Auditable** — every state transition is recorded in an immutable `audit_log` table.
- **Idempotent** — re-running the pipeline at any point produces the same end state.

---

## 4. Storage Layout

```
ssdpool/onedrive-ingest  →  /mnt/ssd/onedrive-ingest/
  staging/               — files downloaded from OneDrive, pending hash + decision
  registry.db            — SQLite hash registry (the system of record)
  token_cache.json       — MSAL OAuth2 token cache (chmod 600)
  delta_cursor           — last Graph API delta link (plain text)

nightfall/media/onedrive-ingest  →  /nightfall/media/onedrive-ingest/
   accepted/              — committed files; ingress queue only
  trash/                 — operator drops files here to trigger rejection

nightfall/media/pictures  →  /nightfall/media/pictures/
   ...                    — permanent library, read-only to ingress (used by Immich and sync-import)
```

**ZFS datasets to create (manual pre-requisite):**

```bash
zfs create -o mountpoint=/mnt/ssd/onedrive-ingest ssdpool/onedrive-ingest
zfs create -o mountpoint=/nightfall/media/onedrive-ingest nightfall/media/onedrive-ingest
```

---

## 5. Hash Registry Design

### Schema

```sql
CREATE TABLE files (
    sha256          TEXT PRIMARY KEY,
    size_bytes      INTEGER NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('accepted', 'rejected', 'purged')),
    original_filename TEXT,
    onedrive_id     TEXT,
    created_at      TEXT NOT NULL,   -- ISO-8601 UTC
    updated_at      TEXT NOT NULL    -- ISO-8601 UTC
);

CREATE TABLE metadata_index (
    -- Fast pre-filter: check if we already processed this OneDrive item
    onedrive_id     TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    modified_time   TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    PRIMARY KEY (onedrive_id)
);

CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256          TEXT NOT NULL,
    action          TEXT NOT NULL,   -- 'accepted', 'rejected', 'purged', 'duplicate_skipped', etc.
    reason          TEXT,
    actor           TEXT NOT NULL,   -- 'pipeline', 'cli', 'trash_watch'
    ts              TEXT NOT NULL    -- ISO-8601 UTC
);

CREATE TABLE accepted_records (
   sha256            TEXT PRIMARY KEY,
   accepted_at       TEXT NOT NULL,
   original_filename TEXT,
   storage_relpath   TEXT,
   account_name      TEXT NOT NULL,
   onedrive_id       TEXT,
   source_modified_time TEXT
);
```

### Properties

- **Idempotent**: `INSERT OR IGNORE` on first insert; status transitions use `UPDATE` + audit append in a single transaction.
- **Auditable**: `audit_log` is append-only; no rows are ever deleted from it.
- **Concurrent-safe**: `BEGIN EXCLUSIVE` transaction for all write paths; SQLite WAL mode.
- **Resilient to restarts**: staging files named `{onedrive_id}.tmp` during download → renamed on completion; a crashed run leaves `.tmp` files that are cleaned up on next start.
- **Move-safe**: `accepted_records` preserves acceptance history even if files are manually moved out of `accepted/`.

---

## 6. Pipeline Behavior

### 6.1 Poll Cycle (every 15 min via systemd timer)

1. Acquire OAuth2 token silently (MSAL refresh token flow).
2. Call Graph API delta endpoint for the configured OneDrive folder.
3. For each changed `file` item:
   a. **Metadata pre-filter**: look up `metadata_index` by `(onedrive_id, size, modified_time)`. If hit and SHA-256 is in `files`, skip — no download needed.
   b. **Download** file to `/mnt/ssd/onedrive-ingest/staging/{onedrive_id}.tmp` (streaming, chunked).
   c. Rename `.tmp` → `{onedrive_id}.{ext}` on success.
   d. **Compute SHA-256** (streaming 64 KB chunks; never loads full file into memory).
   e. **Registry lookup**:
      - `rejected` → delete from staging; append `rejected_duplicate` to `audit_log`.
      - `accepted` → delete from staging; append `duplicate_skipped` to `audit_log`.
      - `unknown` → move to `accepted/YYYY/MM/{filename}`; insert `files` row as `accepted`; insert `accepted_records`; insert `metadata_index` row; append `accepted` to `audit_log`.
4. Persist updated delta cursor.

### 6.2 Live Photo Support in V1

   - Pair detection is required in V1.
   - Ingest tracks likely Live Photo components (for example HEIC/JPEG + MOV) as separate physical files.
   - Pair linkage metadata is persisted for audit and future tooling.
   - Merge/export workflows are deferred to V2.

### 6.3 Sync Hash Import Mode

   - A CLI sync mode imports known hashes from `/nightfall/media/pictures/...`.
   - It reuses `.hashes.sha1` files generated by `nightfall-immich-rmdups.sh`.
   - Imported hashes are used for pre-filtering to reduce unnecessary downloads and hashing.

### 6.4 Rejection Flow

**Via trash directory (filesystem trigger):**
1. Operator places (or moves) a file into `/nightfall/media/onedrive-ingest/trash/`.
2. systemd `.path` unit fires `nightfall-photo-ingress-trash.service`.
3. Service computes SHA-256 of each file in `trash/`.
4. Looks up accepted path from registry, removes from `accepted/`.
5. Updates registry `status = 'rejected'`; appends `audit_log` row with `actor = 'trash_watch'`.
6. Deletes file from `trash/`.

**Via CLI:**
```bash
nightfall-photo-ingress reject <sha256> [--reason "..."]
```
- Idempotent: if already `rejected`, logs and exits cleanly.
- Removes file from `accepted/` if present.
- Updates registry and appends audit_log.

---

## 7. Edge Cases and Mitigations

| Edge case | Mitigation |
|---|---|
| OneDrive rename / move | Graph delta reports `deleted` + new `created`; metadata_index hit on `onedrive_id` prevents re-download after rename if size+mtime match |
| Partial / in-progress upload | Delta API only returns complete items; items without `file.hashes` or missing `@microsoft.graph.downloadUrl` are skipped |
| Name collision in accepted/ | Two different files with same name same month → `{sha256[:8]}-{original_filename}` suffix |
| Delta cursor loss | Fall back to `?token=latest` (last 30 days) or full folder scan; registry idempotency prevents re-ingesting known files |
| Cross-pool atomic move | If staging (SSD) and accepted (HDD) are different ZFS pools: `shutil.copy2` → verify SHA-256 → `unlink` staging; controlled by `STAGING_SAME_POOL` config flag |
| Concurrent poll runs | systemd `Type=oneshot` prevents overlap; SQLite `BEGIN EXCLUSIVE` as secondary guard |
| Auth token expiry | MSAL handles refresh transparently; alert email after ≥3 consecutive auth failures |
| Operator manually moves accepted files away | `accepted_records` table preserves acceptance truth independent of current file location |
| Immich DB purge or upgrade | Pipeline is Immich-independent; permanent library remains the viewer source of truth |
| HDD spin-up discipline | Staging, hashing, and registry all on SSD; HDD only written at accept-commit (atomic move/copy) |

---

## 8. Tech Stack

| Component | Choice | Justification |
|---|---|---|
| Language | Python 3.11+ | Matches nightfall-mcp conventions; stdlib-first; full type hints |
| HTTP client | `httpx` | Streaming / chunked download support; better timeout control than `requests` |
| OAuth2 / token lifecycle | `msal` | Microsoft's official Python library; device-code flow; transparent token refresh; serializable cache |
| Registry | `sqlite3` (stdlib) | ACID transactions; no extra deps; auditable via SQL; portable |
| Schema types | `TypedDict` (stdlib) | Matches nightfall-mcp style — no Pydantic dependency |
| Logging | `logging` + JSON formatter | Structured English logs; feeds journald via stdout |
| Process model | host-level systemd timer + `.path` unit | Matches existing nightfall patterns exactly; no container for V1 |

**Runtime dependencies:** `httpx`, `msal`  
**Dev dependencies:** `pytest`, `pytest-mock`

---

## 9. File Layout (Planned Project Structure)

```
nightfall-photo-ingress/
├── pyproject.toml
├── README.md
├── design/
│   └── architecture.md          ← this file
├── nightfall_photo_ingress/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py                 — config loading from .ini file
│   ├── schemas.py                — TypedDict response types
│   ├── registry.py               — SQLite schema, CRUD, audit log
│   ├── onedrive/
│   │   ├── __init__.py
│   │   ├── auth.py               — MSAL device-code flow, token cache
│   │   └── client.py             — GraphClient: delta pagination + streaming download
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── poller.py             — main poll loop: delta → staging
│   │   └── ingest.py             — hash + registry decision + atomic move
│   └── cli.py                    — entry points: auth-setup, poll, reject, process-trash
├── conf/
│   └── onedrive-ingest.conf      — .ini format; installed to /etc/nightfall/
├── systemd/
│   ├── nightfall-photo-ingress-poll.service
│   ├── nightfall-photo-ingress-poll.timer
│   ├── nightfall-photo-ingress-trash.path
│   └── nightfall-photo-ingress-trash.service
├── install/
│   ├── install.sh
│   └── uninstall.sh
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_registry.py
    ├── test_ingest.py
    └── test_onedrive_client.py
```

---

## 10. Implementation Phases

### Phase 1 — Azure App Registration + Auth

**Goal:** The service can authenticate to Microsoft Graph API from the server without a GUI.

Steps:
1. Register a new app in [Azure portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps):
   - Platform: **Mobile and desktop applications**
   - Redirect URI: `https://login.microsoftonline.com/common/oauth2/nativeclient`
   - Enable **"Allow public client flows"**
   - Add API permissions: `Files.Read` (Microsoft Graph, delegated) + `offline_access`
2. Record the **Application (client) ID** — stored in `/etc/nightfall/onedrive-ingest.conf`
3. Run `nightfall-photo-ingress auth-setup` once on the server:
   - Prints a device-code URL and code
   - Operator opens URL on any browser, signs in
   - Token cache written to `/mnt/ssd/onedrive-ingest/token_cache.json` (mode 0600)

**Deliverable:** `onedrive/auth.py` — MSAL `PublicClientApplication` with device-code flow + silent refresh.

### Phase 2 — Graph API Delta Poller + Staging Download

**Goal:** Reliably discover new/changed files in OneDrive and land them in staging without re-downloading known files.

Steps:
1. `onedrive/client.py`: `GraphClient` wrapping `httpx`; methods:
   - `get_delta(folder_path)` → yields `DeltaItem` TypedDicts
   - `download_file(download_url, dest_path)` → streaming chunked write
2. Delta cursor: persisted to `/mnt/ssd/onedrive-ingest/delta_cursor`; on loss, falls back to `?token=latest`
3. `pipeline/poller.py`: metadata pre-filter using `metadata_index`; staging file naming `{onedrive_id}.tmp` → `{onedrive_id}.{ext}`
4. `--dry-run` flag: lists delta items without downloading

**Deliverable:** `poller.py` discoverable by the systemd timer; `--dry-run` mode for safe testing.

### Phase 3 — SQLite Hash Registry + Ingest Decision Engine

**Goal:** Server-owned content ledger that makes authoritative accept/reject decisions.

Steps:
1. `registry.py`: schema creation, `insert_file()`, `lookup_sha256()`, `mark_rejected()`, `insert_metadata_index()`, `append_audit()`
2. `pipeline/ingest.py`: SHA-256 computation (streaming 64 KB chunks); registry lookup and branch logic; atomic move with cross-pool fallback
3. Transactions: `BEGIN EXCLUSIVE` for all writes; WAL mode enabled on first open

**Deliverable:** Registry fully functional; `pytest tests/test_registry.py` and `pytest tests/test_ingest.py` green.

### Phase 4 — Accepted Queue and Permanent Library Boundary

**Goal:** Keep ingress and permanent library ownership separate, while preserving dedupe history.

Steps:
1. Create ZFS datasets (see Storage Layout above)
2. Ensure ingress has write access to `accepted/` and no write access to `/nightfall/media/pictures/...`
3. Document operator workflow for manually moving files from `accepted/` to permanent library
4. Validate that manually moved files remain blocked from re-download due to registry acceptance history

**Deliverable:** Files can be moved out of accepted queue without regressing dedupe behavior.

### Phase 5 — Trash → Rejected Pipeline

**Goal:** Operator can permanently block content by dropping a file into trash/ or running a CLI command.

Steps:
1. `cli.py`: `reject` subcommand and `process-trash` subcommand
2. `systemd/nightfall-photo-ingress-trash.path`: watches `/nightfall/media/onedrive-ingest/trash/`
3. `systemd/nightfall-photo-ingress-trash.service`: runs `nightfall-photo-ingress process-trash` on activation
4. Both paths share `registry.mark_rejected(sha256, reason, actor)` — idempotent

**Deliverable:** Drop a previously accepted file into trash → it disappears from `accepted/`; re-upload is silently discarded at next poll.

### Phase 6 — Observability + systemd Integration

**Goal:** Operational visibility without requiring active monitoring tooling.

Steps:
1. JSON log formatter: every line includes `ts`, `level`, `component`, `msg`, and context fields (`sha256`, `filename`, `status`) — feeds journald via stdout
2. Status file: write `/run/nightfall-status.d/onedrive-ingest.json` after each poll run — consumed by nightfall-mcp `HealthService`
3. Alert emails: consecutive auth failures (≥3), SSD dataset >90% full, ingest errors
4. Install scripts following nightfall-scripts conventions (`install.sh`, `uninstall.sh`)

**Deliverable:** `pytest tests/` fully green; systemd timers enabled and observable via `journalctl -u nightfall-photo-ingress-poll`.

### Phase 7 — Sync Import + Live Photo Pairing

**Goal:** Reduce duplicate downloads and support modern iPhone defaults in V1.

Steps:
1. Add `sync-import` CLI command to parse `.hashes.sha1` from `/nightfall/media/pictures/...`
2. Persist imported hash index for pre-filter checks during poll
3. Add Live Photo pair detection and pair-link persistence in registry
4. Validate paired/unpaired behavior with HEIC/JPEG + MOV test fixtures

**Deliverable:** Sync import is operational and Live Photo pairing metadata is written in V1.

---

## 11. Configuration File (conf/onedrive-ingest.conf)

```ini
[onedrive]
# Azure app registration client ID (required)
client_id = REPLACE_WITH_CLIENT_ID

# OneDrive folder path to watch (relative to root)
watch_folder = /Camera Roll

# Microsoft identity platform authority
authority = https://login.microsoftonline.com/consumers

[paths]
# SSD-backed working area
staging_dir = /mnt/ssd/onedrive-ingest/staging
registry_db = /mnt/ssd/onedrive-ingest/registry.db
token_cache  = /mnt/ssd/onedrive-ingest/token_cache.json
delta_cursor = /mnt/ssd/onedrive-ingest/delta_cursor

# HDD pool — accepted files and trash trigger
accepted_dir = /nightfall/media/onedrive-ingest/accepted
trash_dir    = /nightfall/media/onedrive-ingest/trash

# Set to true if staging and accepted are on the same ZFS pool
# (enables os.replace() atomic rename; otherwise shutil.copy2 + verify + unlink)
staging_same_pool = false

[polling]
# Folder to use as delta fallback (days to look back when cursor is lost)
delta_fallback_days = 30

[alerts]
# Path to nightfall alert email config
alert_config = /etc/nightfall/alert-email.conf
auth_failure_threshold = 3
```

---

## 12. Verification Checklist

1. `nightfall-photo-ingress auth-setup` completes; token file written at mode 0600
2. `nightfall-photo-ingress poll --dry-run` lists known OneDrive items without downloading
3. End-to-end: single photo ingested; appears in `accepted/YYYY/MM/`; SHA-256 in registry
4. Re-run poll; confirm file NOT downloaded again (metadata_index hit)
5. Move accepted file to trash/; confirm it is removed from accepted/ and registry status = `rejected`
6. Re-upload same photo to OneDrive; run poll; confirm file is silently discarded (audit_log entry: `rejected_duplicate`)
7. `nightfall-photo-ingress reject <sha256>` runs idempotently (no error if already rejected)
8. Move accepted files manually to `/nightfall/media/pictures/...`; confirm no re-download occurs on future polls
9. Run `sync-import`; confirm imported hashes reduce candidate downloads
10. Verify Live Photo pair metadata is recorded for HEIC/JPEG + MOV sets
11. `pytest tests/` all green with mocked HTTP and mocked filesystem
12. `journalctl -u nightfall-photo-ingress-poll` shows structured JSON log output

---

## 13. Open Questions (for Refinement)

1. **Live Photo heuristics**: pick stem+capture-time tolerance and define conflict behavior when multiple MOV candidates exist.
2. **Sync import trust model**: confirm whether imported SHA1 matches should always skip download, or only skip after minimum metadata checks.
3. **Scope of `Files.Read` permission**: `Files.Read` is sufficient for personal accounts via the `/me/drive` endpoint. Confirm whether the specific Camera Roll folder is accessible or if a broader scope is needed.
