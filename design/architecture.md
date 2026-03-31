# nightfall-photo-ingress: Architecture Design

**Status:** DRAFT — pending review  
**Date:** 2026-03-31  
**Author:** ops/copilot design session

---

## Overview

A fully automated, server-side OneDrive-based photo ingest pipeline that feeds into the nightfall archival system. iOS devices upload photos to OneDrive (treated as an untrusted but reliable transport layer). A Linux server running ZFS storage ("nightfall"), Immich, and custom ingest services pulls those files down, validates them, and manages their lifecycle independently of Immich.

**Immich's role is limited to indexing and viewing.** It reads a read-only external library directory; it does not control ingest, lifecycle, or retention decisions.

---

## High-Level Architecture

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
│    accepted/   ← Immich read-only lib   │
│    trash/      ← rejection trigger      │
└─────────────────────────────────────────┘
      │
      │  read-only bind-mount
      ▼
  Immich (LXC container)
  external library → periodic rescan
```

---

## Design Constraints and Goals

- **Fully automated** — no user behavior assumptions on iOS.
- **Robust against Immich changes** — the pipeline operates independently; a fresh Immich DB simply rescans `accepted/`.
- **Reject-once, reject-forever** — a rejected SHA-256 is never ingested again regardless of re-uploads.
- **Minimize unnecessary I/O** — metadata pre-filtering avoids downloading files that are already known; HDD only spun up at accept-commit time.
- **English-only** — all inline comments, logs, and documentation are in English.
- **Auditable** — every state transition is recorded in an immutable `audit_log` table.
- **Idempotent** — re-running the pipeline at any point produces the same end state.

---

## Storage Layout

```
ssdpool/onedrive-ingest  →  /mnt/ssd/onedrive-ingest/
  staging/               — files downloaded from OneDrive, pending hash + decision
  registry.db            — SQLite hash registry (the system of record)
  token_cache.json       — MSAL OAuth2 token cache (chmod 600)
  delta_cursor           — last Graph API delta link (plain text)

nightfall/media/onedrive-ingest  →  /nightfall/media/onedrive-ingest/
  accepted/              — committed files; Immich mounts this read-only
  trash/                 — operator drops files here to trigger rejection
```

**ZFS datasets to create (manual pre-requisite):**

```bash
zfs create -o mountpoint=/mnt/ssd/onedrive-ingest ssdpool/onedrive-ingest
zfs create -o mountpoint=/nightfall/media/onedrive-ingest nightfall/media/onedrive-ingest
```

---

## Hash Registry Design

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
```

### Properties

- **Idempotent**: `INSERT OR IGNORE` on first insert; status transitions use `UPDATE` + audit append in a single transaction.
- **Auditable**: `audit_log` is append-only; no rows are ever deleted from it.
- **Concurrent-safe**: `BEGIN EXCLUSIVE` transaction for all write paths; SQLite WAL mode.
- **Resilient to restarts**: staging files named `{onedrive_id}.tmp` during download → renamed on completion; a crashed run leaves `.tmp` files that are cleaned up on next start.

---

## Pipeline Behavior

### Poll cycle (every 15 min via systemd timer)

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
      - `unknown` → move to `accepted/YYYY/MM/{filename}`; insert `files` row as `accepted`; insert `metadata_index` row; append `accepted` to `audit_log`.
4. Persist updated delta cursor.

### Rejection flow

**Via trash directory (filesystem trigger):**
1. Operator places (or moves) a file into `/nightfall/media/onedrive-ingest/trash/`.
2. systemd `.path` unit fires `nightfall-onedrive-trash.service`.
3. Service computes SHA-256 of each file in `trash/`.
4. Looks up accepted path from registry, removes from `accepted/`.
5. Updates registry `status = 'rejected'`; appends `audit_log` row with `actor = 'trash_watch'`.
6. Deletes file from `trash/`.

**Via CLI:**
```bash
nightfall-onedrive reject <sha256> [--reason "..."]
```
- Idempotent: if already `rejected`, logs and exits cleanly.
- Removes file from `accepted/` if present.
- Updates registry and appends audit_log.

---

## Edge Cases and Mitigations

| Edge case | Mitigation |
|---|---|
| OneDrive rename / move | Graph delta reports `deleted` + new `created`; metadata_index hit on `onedrive_id` prevents re-download after rename if size+mtime match |
| Partial / in-progress upload | Delta API only returns complete items; items without `file.hashes` or missing `@microsoft.graph.downloadUrl` are skipped |
| Name collision in accepted/ | Two different files with same name same month → `{sha256[:8]}-{original_filename}` suffix |
| Delta cursor loss | Fall back to `?token=latest` (last 30 days) or full folder scan; registry idempotency prevents re-ingesting known files |
| Cross-pool atomic move | If staging (SSD) and accepted (HDD) are different ZFS pools: `shutil.copy2` → verify SHA-256 → `unlink` staging; controlled by `STAGING_SAME_POOL` config flag |
| Concurrent poll runs | systemd `Type=oneshot` prevents overlap; SQLite `BEGIN EXCLUSIVE` as secondary guard |
| Auth token expiry | MSAL handles refresh transparently; alert email after ≥3 consecutive auth failures |
| Immich DB purge or upgrade | Pipeline is Immich-independent; `accepted/` directory is the source of truth; Immich rescans automatically |
| HDD spin-up discipline | Staging, hashing, and registry all on SSD; HDD only written at accept-commit (atomic move/copy) |

---

## Tech Stack

| Component | Choice | Justification |
|---|---|---|
| Language | Python 3.11+ | Matches nightfall-mcp conventions; stdlib-first; full type hints |
| HTTP client | `httpx` | Streaming / chunked download support; better timeout control than `requests` |
| OAuth2 / token lifecycle | `msal` | Microsoft's official Python library; device-code flow; transparent token refresh; serializable cache |
| Registry | `sqlite3` (stdlib) | ACID transactions; no extra deps; auditable via SQL; portable |
| Schema types | `TypedDict` (stdlib) | Matches nightfall-mcp style — no Pydantic dependency |
| Logging | `logging` + JSON formatter | Structured English logs; feeds journald via stdout |
| Process model | systemd timer + `.path` unit | Matches existing nightfall patterns exactly |

**Runtime dependencies:** `httpx`, `msal`  
**Dev dependencies:** `pytest`, `pytest-mock`

---

## File Layout (planned project structure)

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
│   ├── nightfall-onedrive-poll.service
│   ├── nightfall-onedrive-poll.timer
│   ├── nightfall-onedrive-trash.path
│   └── nightfall-onedrive-trash.service
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

## Implementation Phases

### Phase 1 — Azure App Registration + Auth

**Goal:** The service can authenticate to Microsoft Graph API from the server without a GUI.

Steps:
1. Register a new app in [Azure portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps):
   - Platform: **Mobile and desktop applications**
   - Redirect URI: `https://login.microsoftonline.com/common/oauth2/nativeclient`
   - Enable **"Allow public client flows"**
   - Add API permissions: `Files.Read` (Microsoft Graph, delegated) + `offline_access`
2. Record the **Application (client) ID** — stored in `/etc/nightfall/onedrive-ingest.conf`
3. Run `nightfall-onedrive auth-setup` once on the server:
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

### Phase 4 — ZFS + Immich External Library Wiring

**Goal:** Accepted files are visible in Immich with zero manual intervention.

Steps:
1. Create ZFS datasets (see Storage Layout above)
2. Add read-only bind-mount to `containers/immich/opt/immich/docker-compose.yml`:
   ```yaml
   - /nightfall/media/onedrive-ingest/accepted:/usr/src/app/onedrive-library:ro
   ```
3. Register external library in Immich via API:
   ```
   POST /api/library
   { "name": "OneDrive Ingest", "importPaths": ["/usr/src/app/onedrive-library"] }
   ```
4. Verify: delete a file from `accepted/` → Immich marks it offline on next scan (no schema migration required)

**Deliverable:** First end-to-end photo visible in Immich after a successful poll cycle.

### Phase 5 — Trash → Rejected Pipeline

**Goal:** Operator can permanently block content by dropping a file into trash/ or running a CLI command.

Steps:
1. `cli.py`: `reject` subcommand and `process-trash` subcommand
2. `systemd/nightfall-onedrive-trash.path`: watches `/nightfall/media/onedrive-ingest/trash/`
3. `systemd/nightfall-onedrive-trash.service`: runs `nightfall-onedrive process-trash` on activation
4. Both paths share `registry.mark_rejected(sha256, reason, actor)` — idempotent

**Deliverable:** Drop a previously accepted file into trash → it disappears from `accepted/`; re-upload is silently discarded at next poll.

### Phase 6 — Observability + systemd Integration

**Goal:** Operational visibility without requiring active monitoring tooling.

Steps:
1. JSON log formatter: every line includes `ts`, `level`, `component`, `msg`, and context fields (`sha256`, `filename`, `status`) — feeds journald via stdout
2. Status file: write `/run/nightfall-status.d/onedrive-ingest.json` after each poll run — consumed by nightfall-mcp `HealthService`
3. Alert emails: consecutive auth failures (≥3), SSD dataset >90% full, ingest errors
4. Install scripts following nightfall-scripts conventions (`install.sh`, `uninstall.sh`)

**Deliverable:** `pytest tests/` fully green; systemd timers enabled and observable via `journalctl -u nightfall-onedrive-poll`.

---

## Configuration File (conf/onedrive-ingest.conf)

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

## Verification Checklist

1. `nightfall-onedrive auth-setup` completes; token file written at mode 0600
2. `nightfall-onedrive poll --dry-run` lists known OneDrive items without downloading
3. End-to-end: single photo ingested; appears in `accepted/YYYY/MM/`; SHA-256 in registry; visible in Immich after scan
4. Re-run poll; confirm file NOT downloaded again (metadata_index hit)
5. Move accepted file to trash/; confirm it is removed from accepted/ and registry status = `rejected`
6. Re-upload same photo to OneDrive; run poll; confirm file is silently discarded (audit_log entry: `rejected_duplicate`)
7. `nightfall-onedrive reject <sha256>` runs idempotently (no error if already rejected)
8. `pytest tests/` all green with mocked HTTP and mocked filesystem
9. `journalctl -u nightfall-onedrive-poll` shows structured JSON log output

---

## Open Questions (for refinement)

1. **Immich library path**: Should the new `accepted/` be a sub-path inside the existing `library` mount, or a separate mount point? Separate mount is recommended to avoid mixing library sources.
2. **iOS folder structure**: Does iOS upload to a flat `/Camera Roll/` or does it create dated sub-folders? The delta API handles this recursively regardless, but affects accepted/ layout expectations.
3. **Scope of `Files.Read` permission**: `Files.Read` is sufficient for personal accounts via the `/me/drive` endpoint. Confirm whether the specific Camera Roll folder is accessible or if a broader scope is needed.
4. **Multi-account support**: Is this pipeline expected to support multiple iOS devices / OneDrive accounts? Current design handles one account; multi-account would require per-account token caches and namespaced staging dirs.
