# photo-ingress: Architecture Design

**Status:** navigation index — content extracted to topic documents  
**Date:** 2026-03-31  
**Updated:** 2026-04-03  
**Author:** ops/copilot design session

> This document is retained as a navigation index. All major sections have been extracted
> to focused topic documents under `design/architecture/`, `design/specs/`, `design/domain/`,
> and `design/rationale/`. Refer to those documents for authoritative content.

---

## Document Map

| Topic | Document |
|---|---|
| Naming matrix and glossary | [design/domain/glossary.md](domain/glossary.md) |
| Design constraints and goals | [design/domain/constraints.md](domain/constraints.md) |
| High-level pipeline (data flow) | [design/architecture/data-flow.md](architecture/data-flow.md) |
| Storage topology (ZFS datasets, mount layout) | [design/architecture/storage-topology.md](architecture/storage-topology.md) |
| Registry schema and properties | [design/specs/registry.md](specs/registry.md) |
| Ingest spec (poll cycle, sync import) | [design/specs/ingest.md](specs/ingest.md) |
| Accept flow | [design/specs/accept.md](specs/accept.md) |
| Reject flow | [design/specs/reject.md](specs/reject.md) |
| Purge flow | [design/specs/purge.md](specs/purge.md) |
| Lifecycle journal and crash recovery | [design/architecture/lifecycle.md](architecture/lifecycle.md) |
| Error taxonomy and resilience | [design/architecture/error-model.md](architecture/error-model.md) |
| Observability internals | [design/architecture/observability.md](architecture/observability.md) |
| State machine | [design/architecture/state-machine.md](architecture/state-machine.md) |
| Live Photo pair lifecycle | [design/architecture/live-photo-pair-lifecycle.md](architecture/live-photo-pair-lifecycle.md) |
| Schema and migrations | [design/architecture/schema-and-migrations.md](architecture/schema-and-migrations.md) |
| Tech stack rationale and tradeoffs | [design/rationale/tradeoffs.md](rationale/tradeoffs.md) |
| Web control plane docs | [design/web/](web/) |

---

## Related Documents

- [Web Control Plane Architecture Phase 1](web/webui-architecture-phase1.md)
- [Web Control Plane Integration Plan](../planning/planned/web-control-plane-integration-plan.md)

---

## 1. Overview

A fully automated, server-side OneDrive-based photo ingest pipeline that feeds into the nightfall archival system. iOS devices upload photos to OneDrive (treated as an untrusted but reliable transport layer). A Linux server running ZFS storage ("nightfall"), Immich, and custom ingest services pulls those files down, validates them, and manages their lifecycle independently of Immich.

**Immich's role is limited to indexing and viewing permanent library content only.** The ingress service writes new content into a pending queue. Human operators explicitly transition pending content to accepted or rejected. Rejected content is retained on disk until explicit purge.

For the canonical naming matrix, see [design/domain/glossary.md](domain/glossary.md).

### 1.1 Naming Matrix (Canonical V2)

| Scope | Canonical Name | Notes |
|---|---|---|
| Project and service | `photo-ingress` | Primary name in docs, CLI, and operational language |
| Source adapter | `onedrive` | Current adapter; kept explicit in config and module names |
| Python package | `nightfall_photo_ingress` | Keeps namespace alignment with existing nightfall Python projects |
| CLI command | `nightfall-photo-ingress` | Main operational command (binary installed under `/opt/nightfall-photo-ingress/bin/`) |
| Config file | `/etc/nightfall/photo-ingress.conf` | Single versioned INI file |
| systemd units | `nightfall-photo-ingress.service`, `nightfall-photo-ingress.timer`, `nightfall-photo-ingress-trash.path`, `nightfall-photo-ingress-trash.service` | systemd-managed runtime inside the `photo-ingress` LXC container |
| SSD ZFS dataset (container) | `ssdpool/photo-ingress` | Always-on staging, cursors, token caches, registry |
| SSD mountpoint | `/mnt/ssd/photo-ingress` | Working set for low-latency operations |
| HDD ZFS dataset (container) | `nightfall/media/photo-ingress` | Queue/trash boundary on nightfall pool |
| HDD mountpoint | `/nightfall/media/photo-ingress` | `pending/`, `accepted/`, `rejected/`, and `trash/` live here |
| Permanent library root | `/nightfall/media/pictures` | Read-only to ingress, indexed by Immich |
| Health status file | `/run/nightfall-status.d/photo-ingress.json` | Exported each poll cycle |

---

## 2. High-Level Architecture

> **Extracted** → [design/architecture/data-flow.md](architecture/data-flow.md) and [design/architecture/storage-topology.md](architecture/storage-topology.md)

```
iOS Camera Roll
      │
      │  (automatic background upload)
      ▼
  OneDrive (personal Microsoft account)
      │
      │  Microsoft Graph API — delta poll on operational cadence (8-24h in production)
      ▼
┌─────────────────────────────────────────┐
│           nightfall server              │
│                                         │
│  /mnt/ssd/photo-ingress/staging/        │  ← SSD; temp download area
│       │                                 │
│       │  SHA-256 hash                   │
│       │  registry lookup                │
│       ▼                                 │
│  registry.db (SQLite, SSD)              │  ← authoritative content ledger
│       │                                 │
│       ├─ rejected → delete from staging │
│       ├─ pending  → delete from staging │
│       ├─ accepted → delete from staging │
│       ├─ purged   → delete from staging │
│       └─ unknown  → move to pending/    │
│                    + insert registry    │
│                                         │
│  /nightfall/media/photo-ingress/        │  ← HDD pool
│    pending/    ← ingest destination      │
│    accepted/   ← explicit accept target  │
│    rejected/   ← retained rejected files │
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

> **Extracted** → [design/domain/constraints.md](domain/constraints.md)

- **Fully automated** — no user behavior assumptions on iOS.
- **Robust against Immich changes** — the pipeline operates independently; a fresh Immich DB simply rescans the permanent library.
- **Reject-once, reject-forever** — a rejected SHA-256 is never ingested again regardless of re-uploads.
- **Explicit acceptance** — no automatic transition from unknown to accepted.
- **Accepted-history persistence** — accepted content remains blocked from re-download even after operator relocation.
- **Minimize unnecessary I/O** — metadata pre-filtering avoids downloading files that are already known; HDD is only touched for queue transitions.
- **Legacy-free v2 boundary** — no accepted-first config fallbacks, no silent auto-accept, and no in-place registry upgrade from pre-v2 schemas.
- **English-only** — all inline comments, logs, and documentation are in English.
- **Auditable** — every state transition is recorded in an immutable `audit_log` table.
- **Idempotent** — re-running the pipeline at any point produces the same end state.

---

## 4. Storage Layout

> **Extracted** → [design/architecture/storage-topology.md](architecture/storage-topology.md)

```
ssdpool/photo-ingress  →  /mnt/ssd/photo-ingress/
  staging/               — files downloaded from OneDrive, pending hash + decision
  registry.db            — SQLite hash registry (the system of record)
  token_cache.json       — MSAL OAuth2 token cache (chmod 600)
   delta_cursor           — per-account delta traversal checkpoint (plain text)

nightfall/media/photo-ingress  →  /nightfall/media/photo-ingress/
   pending/               — unknown-hash ingest destination (operator review queue)
   accepted/              — explicit accept destination
   rejected/              — retained rejected artifacts (until purge)
   trash/                 — operator drops files here to trigger rejection flow

nightfall/media/pictures  →  /nightfall/media/pictures/
   ...                    — permanent library, read-only to ingress (used by Immich and sync-import)
```

**ZFS datasets to create (manual pre-requisite):**

```bash
zfs create -o mountpoint=/mnt/ssd/photo-ingress ssdpool/photo-ingress
zfs create -o mountpoint=/nightfall/media/photo-ingress nightfall/media/photo-ingress
```

---

## 5. Hash Registry Design

> **Extracted** → [design/specs/registry.md](specs/registry.md)

### Schema

**Core tables (schema version 2 — bootstrapped at first `initialize()` call):**

```sql
CREATE TABLE IF NOT EXISTS files (
    sha256            TEXT PRIMARY KEY,
    size_bytes        INTEGER NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'rejected', 'purged')),
    original_filename TEXT,
    current_path      TEXT,           -- last known filesystem path (advisory; not canonical identity)
    first_seen_at     TEXT NOT NULL,  -- ISO-8601 UTC
    updated_at        TEXT NOT NULL   -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS metadata_index (
    account_name  TEXT NOT NULL,
    onedrive_id   TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    modified_time TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    created_at    TEXT NOT NULL,      -- ISO-8601 UTC
    updated_at    TEXT NOT NULL,      -- ISO-8601 UTC
    PRIMARY KEY (account_name, onedrive_id)
);

CREATE TABLE IF NOT EXISTS accepted_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256      TEXT NOT NULL,
    account     TEXT NOT NULL,
    source_path TEXT NOT NULL,        -- path at time of acceptance
    accepted_at TEXT NOT NULL,        -- ISO-8601 UTC
    FOREIGN KEY (sha256) REFERENCES files(sha256)
);

CREATE TABLE IF NOT EXISTS file_origins (
    account      TEXT NOT NULL,
    onedrive_id  TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    path_hint    TEXT,
    first_seen_at TEXT NOT NULL,      -- ISO-8601 UTC
    last_seen_at  TEXT NOT NULL,      -- ISO-8601 UTC
    PRIMARY KEY (account, onedrive_id),
    FOREIGN KEY (sha256) REFERENCES files(sha256)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256       TEXT,
    account_name TEXT,
    action       TEXT NOT NULL,       -- e.g. 'pending', 'accepted', 'rejected', 'purged', 'discard_accepted'
    reason       TEXT,
    details_json TEXT,
    actor        TEXT NOT NULL,       -- runtime actor label, e.g. 'ingest_pipeline', 'cli', 'trash_watch', 'api'
    ts           TEXT NOT NULL        -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS live_photo_pairs (
    pair_id      TEXT PRIMARY KEY,
    account      TEXT NOT NULL,
    stem         TEXT NOT NULL,
    photo_sha256 TEXT NOT NULL,
    video_sha256 TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('paired', 'pending', 'accepted', 'rejected', 'purged')),
    created_at   TEXT NOT NULL,       -- ISO-8601 UTC
    updated_at   TEXT NOT NULL,       -- ISO-8601 UTC
    FOREIGN KEY (photo_sha256) REFERENCES files(sha256),
    FOREIGN KEY (video_sha256) REFERENCES files(sha256)
);

CREATE TABLE IF NOT EXISTS external_hash_cache (
    account_name   TEXT NOT NULL,
    source_relpath TEXT NOT NULL,
    hash_algo      TEXT NOT NULL,
    hash_value     TEXT NOT NULL,
    verified_sha256 TEXT,
    first_seen_at  TEXT NOT NULL,     -- ISO-8601 UTC
    updated_at     TEXT NOT NULL,     -- ISO-8601 UTC
    PRIMARY KEY (account_name, source_relpath, hash_algo, hash_value)
);

-- Triggers enforcing append-only invariant on audit_log
CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(FAIL, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(FAIL, 'audit_log is append-only');
END;
```

**Optional/additive table (created by `_ensure_optional_tables()` on `initialize()`):**

```sql
CREATE TABLE IF NOT EXISTS ingest_terminal_audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_run_id TEXT NOT NULL,
    sequence_no  INTEGER NOT NULL,
    account      TEXT NOT NULL,
    onedrive_id  TEXT NOT NULL,
    sha256       TEXT,
    action       TEXT NOT NULL,
    reason       TEXT,
    actor        TEXT NOT NULL,
    ts           TEXT NOT NULL        -- ISO-8601 UTC
);
```

### Properties

- **Idempotent**: `INSERT OR IGNORE` / `ON CONFLICT DO UPDATE` on first insert; status transitions use `UPDATE` + audit append in one `BEGIN IMMEDIATE` transaction.
- **Auditable**: `audit_log` is append-only; enforcement is at the DB layer via SQL triggers (`trg_audit_log_no_update`, `trg_audit_log_no_delete`).
- **Concurrent-safe**: `BEGIN IMMEDIATE` transaction for all write paths; SQLite WAL mode enabled at first open.
- **Resilient to restarts**: staging files named `{onedrive_id}.tmp` during download → renamed on completion; a crashed run leaves `.tmp` files that are cleaned up on next start via `StagingDriftReport`.
- **Move-safe**: `accepted_records` preserves acceptance history even if files are manually moved out of `accepted/`.
- **Pending-first**: `accepted_records` is written only on explicit accept, never on unknown ingest.
- **Provenance-tracked**: `file_origins` records the `(account, onedrive_id)` → `sha256` mapping for every file ever encountered, independent of current status.
- **Advisory hash import**: `external_hash_cache` stores SHA1 hashes imported from `.hashes.sha1` files; `verified_sha256` column is populated after first-download SHA-256 confirmation, converting an advisory hint to a confirmed identity mapping.

---

## 6. Pipeline Behavior

> **Extracted** → [design/specs/ingest.md](specs/ingest.md), [design/specs/accept.md](specs/accept.md), [design/specs/reject.md](specs/reject.md), [design/specs/purge.md](specs/purge.md), [design/architecture/lifecycle.md](architecture/lifecycle.md)

### 6.1 Poll Cycle

1. Acquire OAuth2 token silently (MSAL refresh token flow).
2. Call Graph API delta endpoint for the configured OneDrive folder.
3. For each changed `file` item:
   a. **Metadata pre-filter**: look up `metadata_index` by `(account_name, onedrive_id, size, modified_time)`. If hit and SHA-256 is in `files`, skip — no download needed.
   b. **Download** file to `/mnt/ssd/photo-ingress/staging/{onedrive_id}.tmp` (streaming, chunked).
   c. Rename `.tmp` → `{onedrive_id}.{ext}` on success.
   c1. Each downloaded file is wrapped in a `DownloadedHandoffCandidate` record (the production-owned M3→M4 boundary contract: `account_name`, `onedrive_id`, `original_filename`, `relative_path`, `modified_time`, `size_bytes`, `staging_path`). The ingest engine processes these immediately within the same poll run.
   d. **Compute SHA-256** (streaming 64 KB chunks; never loads full file into memory). The lifecycle journal (`IngestOperationJournal`) records phase transitions (`download_started`, `hash_computed`, `decision_applied`, `finalized`) for crash-boundary recovery.
    e. **Blocklist enforcement (Chunk 5)**:
        - enabled blocklist match (`filename` glob or `regex`) → delete from staging; persist file as `rejected`; append `rejected` with reason `block_rule:<type>:<pattern>`.
    f. **Registry lookup** (if not blocklist-rejected):
        - `rejected` → delete from staging; append `discard_rejected` to `audit_log`.
        - `pending`  → delete from staging; append `discard_pending` to `audit_log`.
        - `accepted` → delete from staging; append `discard_accepted` to `audit_log`.
        - `purged`   → delete from staging; append `discard_purged` to `audit_log`.
        - `unknown` → move to `pending/YYYY/MM/{filename}`; insert `files` row as `pending`; insert `metadata_index` row; append `pending` to `audit_log`.
4. Persist cursor checkpoints with a commit-gated streaming sequence per page:
   - fetch one page,
   - evaluate prefilter and ingest outcomes for that page,
   - commit registry/storage side effects,
   - then persist `nextLink` cursor for the next page.
5. On chain completion (`deltaLink` reached), persist the `deltaLink` as the committed cursor.

### 6.1.1 Authoritative Cursor Commit Rule

The streaming page-commit model is authoritative. Cursor advancement is a commit acknowledgement, not a fetch acknowledgement.

- Never advance cursor before page ingest side effects are durable.
- If a poll run is interrupted before cursor advance, replaying the same page must be safe via registry idempotency.
- If interrupted after cursor advance, the next run resumes from the next page without missing committed work.

Account execution rule:
- Enabled accounts are processed serially in declaration order from the configuration file.

### 6.2 Live Photo Support

   - Pair detection is required in v2.
   - Ingest tracks likely Live Photo components (for example HEIC/JPEG + MOV) as separate physical files.
   - Pairing heuristics are configurable with current runtime defaults:
     - `live_photo_capture_tolerance_seconds = 3`
     - `live_photo_stem_mode = exact_stem`
     - `live_photo_component_order = photo_first`
     - `live_photo_conflict_policy = nearest_capture_time`
   - The runtime currently supports only these validated defaults.
   - Pair linkage metadata is persisted for audit and future tooling.
   - Merge/export workflows are deferred beyond v2.0.

### 6.3 Sync Hash Import Mode

   - A CLI sync mode imports known hashes from `/nightfall/media/pictures/...`.
   - It reuses `.hashes.sha1` files generated by `nightfall-immich-rmdups.sh`.
   - Missing, stale, or invalid `.hashes.sha1` files are handled by re-hashing that directory for import only; the permanent library remains read-only.
   - Imported hashes are used for pre-filtering to reduce unnecessary downloads and hashing.
   - `verify_sha256_on_first_download = true` (default) requires one server-side SHA-256 verification for advisory SHA1 matches before future metadata-only skips.

### 6.4 Rejection Flow

**Via trash directory (filesystem trigger):**
1. Operator places (or moves) a file into `/nightfall/media/photo-ingress/trash/`.
2. systemd `.path` unit fires `nightfall-photo-ingress-trash.service`.
3. Service computes SHA-256 of each file in `trash/`.
4. If a known queue artifact exists, it is moved to `rejected/`.
5. If unknown, the trash artifact itself is moved to `rejected/` and registered as `rejected`.
6. Registry `status = 'rejected'`; appends `audit_log` row with `actor = 'trash_watch'`.

**Via CLI:**
```bash
nightfall-photo-ingress reject <sha256> [--reason "..."]
```
- Idempotent: if already `rejected`, logs and exits cleanly.
- Moves current queue file to `rejected/` if present.
- Updates registry and appends audit log.

### 6.5 Accept and Purge Flows

**Accept (explicit operator transition):**
```bash
nightfall-photo-ingress accept <sha256> [--reason "..."]
```
- Requires current status `pending`.
- Moves file from `pending/` to `accepted/` using `accepted_storage_template`.
- Transitions status `pending -> accepted` and writes `accepted_records`.

**Purge (explicit destructive transition):**
```bash
nightfall-photo-ingress purge <sha256> [--reason "..."]
```
- Requires current status `rejected`.
- Deletes retained file from `rejected/` with root-containment safety checks.
- Transitions status `rejected -> purged`.

### 6.6 Version Boundary and Bootstrap

- `config_version = 2` is mandatory.
- `pending_path`, `accepted_path`, `rejected_path`, and `trash_path` must be configured explicitly and must remain distinct.
- v2.0 does not upgrade pre-v2 registries in place. Deployments must bootstrap a fresh `registry.db` at schema version 2.
- Any stale registry `current_path` outside managed queue roots is treated as an operator error and accept/reject flows fail closed.

---

## 7. Edge Cases and Mitigations

> **Extracted** → [design/architecture/error-model.md](architecture/error-model.md)

| Edge case | Mitigation |
|---|---|
| OneDrive rename / move | Graph delta reports `deleted` + new `created`; metadata_index hit on `onedrive_id` prevents re-download after rename if size+mtime match |
| Partial / in-progress upload | Delta API only returns complete items; items without `file.hashes` or missing `@microsoft.graph.downloadUrl` are skipped |
| Name collision in pending/accepted/rejected | Template rendering + collision-safe suffixing preserves uniqueness |
| Delta cursor loss | Fall back to `?token=latest` (last 30 days) or full folder scan; registry idempotency prevents re-ingesting known files |
| Cross-pool atomic move | Ingest and accept transitions choose rename vs copy-verify-unlink based on filesystem topology |
| Concurrent poll runs | Explicit global process lock serializes full poll runs across CLI and timer paths; `Type=oneshot` is a secondary defense |
| Auth token expiry | MSAL handles refresh transparently; alert email after ≥3 consecutive auth failures |
| Operator manually moves accepted files away | `accepted_records` table preserves acceptance truth independent of current file location |
| Rejected retention and purge safety | Rejected artifacts remain in `rejected/` until explicit purge; purge rejects out-of-root paths |
| Immich DB purge or upgrade | Pipeline is Immich-independent; permanent library remains the viewer source of truth |
| HDD spin-up discipline | Staging, hashing, and registry all on SSD; HDD writes occur on pending/accept/reject transitions only |

---

## 8. Tech Stack

> **Extracted** → [design/rationale/tradeoffs.md](rationale/tradeoffs.md)

| Component | Choice | Justification |
|---|---|---|
| Language | Python 3.11+ | Matches nightfall-mcp conventions; stdlib-first; full type hints |
| HTTP client | `httpx` | Streaming / chunked download support; better timeout control than `requests` |
| OAuth2 / token lifecycle | `msal` | Microsoft's official Python library; device-code flow; transparent token refresh; serializable cache |
| Registry | `sqlite3` (stdlib) | ACID transactions; no extra deps; auditable via SQL; portable |
| Schema types | `TypedDict` (stdlib) | Matches nightfall-mcp style — no Pydantic dependency |
| Logging | `logging` + JSON formatter | Structured English logs; feeds journald via stdout |
| Process model | systemd timer + `.path` unit inside `photo-ingress` LXC | Matches current production/staging deployment model |

**Runtime dependencies:** `httpx`, `msal`  
**Dev dependencies:** `pytest`, `pytest-mock`

---

## 9. Source and Project Layout (As-Implemented)

```
nightfall-photo-ingress/
├── pyproject.toml               — package metadata, dependencies, entry point
├── README.md
├── ARCHITECTURE.md              — module-level overview (cross-ref to this file)
├── design/                      — authoritative architecture documents (this tree)
│   ├── domain-architecture-overview.md   ← this file
│   ├── cli-config-specification.md
│   ├── architecture-decision-log.md
│   ├── webui-architecture-phase1.md
│   ├── web-control-plane-architecture-phase2.md
│   ├── web-control-plane-architecture-phase3.md
│   └── webui-component-mapping-phase1.md
├── src/
│   └── nightfall_photo_ingress/
│       ├── __init__.py          — package version (`__version__ = "2.0.0"`)
│       ├── __main__.py          — `python -m nightfall_photo_ingress` entry
│       ├── cli.py               — CLI entrypoint; all operator subcommands
│       ├── config.py            — INI config loading, validation, typed models
│       ├── logging_bootstrap.py — JSON/human log mode selection
│       ├── live_photo.py        — Live Photo pairing heuristics and deferred queue
│       ├── reject.py            — accept/reject/purge/process-trash operator flows
│       ├── status.py            — atomic status snapshot export
│       ├── sync_import.py       — advisory SHA1 import from permanent library
│       ├── domain/              — source-agnostic core business logic
│       │   ├── __init__.py
│       │   ├── registry.py      — SQLite system-of-record (schema, CRUD, audit)
│       │   ├── storage.py       — path templating, cross-pool commit workflows
│       │   ├── ingest.py        — IngestDecisionEngine (hash-based policy matrix)
│       │   ├── journal.py       — append-only JSONL crash-recovery lifecycle log
│       │   └── migrations/      — schema migration framework scaffold
│       ├── adapters/            — pluggable external data source adapters
│       │   └── onedrive/
│       │       ├── __init__.py
│       │       ├── auth.py      — MSAL device-code flow, serializable token cache
│       │       ├── client.py    — GraphClient: delta pagination, download, retries
│       │       ├── retry.py     — RetryPolicy dataclass and backoff logic
│       │       ├── cache_lock.py — per-account singleton lock for poll safety
│       │       ├── errors.py    — structured error taxonomy, URL redaction
│       │       └── safe_logging.py — credential/URL scrubbing for log extras
│       └── runtime/             — infrastructure and orchestration helpers
│           └── process_lock.py  — global fcntl advisory lock for poll serialization
├── conf/
│   └── photo-ingress.conf.example  — annotated example config
├── systemd/                         — production systemd units
│   ├── nightfall-photo-ingress.service
│   ├── nightfall-photo-ingress.timer
│   ├── nightfall-photo-ingress-trash.path
│   └── nightfall-photo-ingress-trash.service
├── install/
│   ├── install.sh               — LXC container bootstrap and service install
│   └── uninstall.sh
├── docs/                        — operator-facing documentation
│   ├── operations-runbook.md
│   └── app-registration-design.md
├── planning/                    — planning and roadmap artifacts
│   ├── implemented/
│   ├── planned/
│   ├── proposed/
│   └── superseeded/
├── review/                      — audit and compliance review artifacts
└── tests/
    ├── conftest.py
    ├── unit/                    — unit test suite (per-module)
    ├── integration/             — M3+M4 integration harness
    ├── staging/                 — staging environment test harness
    └── staging-flow/            — flowctl staging contract tests
```

---

## 10. Implementation Delivery Record

The following phases were used to drive implementation. All phases are delivered as of
2026-04-01. This section is retained as a historical record; it is not a forward plan.

| Phase | Scope | Status |
|-------|-------|--------|
| 1 — Auth | MSAL device-code flow, token cache, `auth-setup` CLI | Delivered |
| 2 — Delta Poller + Staging | GraphClient, delta pagination, staging downloads, cursor persistence | Delivered |
| 3 — Registry + Ingest Engine | SQLite schema v2, IngestDecisionEngine, hash-based policy matrix | Delivered |
| 4 — Queue Boundaries | Pending queue, accepted queue, permanent library boundary enforcement | Delivered |
| 5 — Operator Rejection Flows | `reject`, `accept`, `purge`, `process-trash` CLI; trash path unit | Delivered |
| 6 — Observability | JSON logger, status snapshot, run-ID threading, diagnostic counters | Delivered |
| 7 — Sync Import + Live Photo | `sync-import` CLI, `external_hash_cache`, Live Photo pairing heuristics | Delivered |

For current planning and next-step work (Modules 5–8 in the implementation roadmap,
web control plane phases), see `planning/`.

For compliance audit artifacts covering Modules 3 and 4, see `review/`.

---

## 11. Configuration File (conf/photo-ingress.conf)

The full config spec, including all required keys, defaults, and validation rules, is in
[design/cli-config-specification.md](cli-config-specification.md).

The format uses a `[core]` global section plus one `[account.<name>]` section per OneDrive
account. Below is a minimal representative example:

```ini
[core]
config_version = 2
poll_interval_minutes = 720
staging_path = /mnt/ssd/photo-ingress/staging
pending_path = /nightfall/media/photo-ingress/pending
accepted_path = /nightfall/media/photo-ingress/accepted
rejected_path = /nightfall/media/photo-ingress/rejected
trash_path = /nightfall/media/photo-ingress/trash
registry_path = /mnt/ssd/photo-ingress/registry.db
storage_template = {yyyy}/{mm}/{original}
accepted_storage_template = {yyyy}/{mm}/{original}
staging_on_same_pool = false
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

[logging]
log_level = INFO
console_format = json
```

Key properties:
- `config_version = 2` is mandatory; the runtime rejects any other value.
- Token cache and delta cursor paths must be unique per account.
- `process_accounts_in_config_order = true` (default) preserves declaration order.
- All path fields are validated for existence at startup.

---

## 12. Verification Checklist

1. `nightfall-photo-ingress auth-setup --account <name>` completes; token file written at mode 0600
2. `nightfall-photo-ingress poll --dry-run` lists known OneDrive items without downloading
3. End-to-end: single photo ingested; appears in `pending/YYYY/MM/`; SHA-256 in registry with status `pending`
4. Re-run poll; confirm file NOT downloaded again (metadata_index hit)
5. `nightfall-photo-ingress accept <sha256>` transitions pending to accepted; file moves to `accepted/`
6. Move accepted file to `trash/`; confirm it is removed from `accepted/` and registry status = `rejected`
7. Re-upload same photo to OneDrive; run poll; confirm file is silently discarded (audit_log entry: `discard_rejected`)
8. `nightfall-photo-ingress reject <sha256>` runs idempotently (no error if already rejected)
9. `nightfall-photo-ingress purge <sha256>` only purges within rejected root and marks status `purged`
10. Move accepted files manually to `/nightfall/media/pictures/...`; confirm no re-download on future polls
11. Run `nightfall-photo-ingress sync-import`; confirm imported hashes reduce candidate downloads
12. Verify Live Photo pair metadata is recorded for HEIC/JPEG + MOV sets
13. `pytest tests/` all green with mocked HTTP and mocked filesystem
14. `journalctl -u nightfall-photo-ingress.service` shows structured JSON log output

---

## 13. Open Questions (for Refinement)

1. **Live Photo heuristics scope**: confirm whether V1 should remain fixed to defaults only, while still validating all related config parameters. *(Partially answered: runtime enforces defaults; config keys are validated but runtime rejects non-default values.)*
2. **Sync import trust model**: confirm whether imported SHA1 matches should always skip download, or only skip after minimum metadata checks. *(Resolved: `verify_sha256_on_first_download = true` requires one SHA-256 confirmation before advisory SHA1 matches gate future skips.)*
3. **Scope of `Files.Read` permission**: `Files.Read` is sufficient for personal accounts via the `/me/drive` endpoint. Confirm whether the specific Camera Roll folder is accessible or if a broader scope is needed.

---

## 14. Ingest Lifecycle Journal

> **Extracted** → [design/architecture/lifecycle.md](architecture/lifecycle.md)

The `IngestOperationJournal` (`domain/journal.py`) is a per-operation append-only JSONL
file that records coarse phase transitions during the staging-to-pending commit path. It
exists as a crash-boundary recovery mechanism, separate from and complementary to the
SQLite `audit_log`.

### Role and relationship to audit_log

| Concern | IngestOperationJournal | audit_log |
|---------|----------------------|-----------|
| Scope | One file per ingest operation, ephemeral | All state transitions, permanent |
| Format | JSONL on disk | SQLite rows |
| Retention | Cleared after successful commit | Append-only, never deleted |
| Purpose | Crash recovery / replay | Audit, operator visibility |

### Phase sequence

Each ingest operation for one `DownloadedHandoffCandidate` records the following phases
in order:

1. `download_started` — download began (recorded by adapter before first byte written)
2. `hash_computed` — SHA-256 computed and canonical identity established
3. `decision_applied` — registry policy decision resolved (pending/discard/duplicate)
4. `finalized` — file moved to destination and registry row committed

### Crash recovery

On startup (before the first poll), `IngestDecisionEngine.reconcile_interrupted_operations()`
reads all journal records and replays any operation that reached `hash_computed` or
`decision_applied` but not `finalized`. Replay is safe because all downstream operations
are idempotent via `ON CONFLICT DO UPDATE` and `INSERT OR IGNORE` guards.

If `journal_path` is not configured, the journal is disabled and crash recovery falls back
to manual staging reconciliation.

### StagingDriftReport

The `StagingDriftReport` dataclass classifies the staging directory content on each
reconciliation pass:

| Classification | Meaning |
|---------------|---------|
| `stale_temp_count` | `.tmp` files from interrupted downloads; safe to delete |
| `completed_unpersisted_count` | Downloaded files with no journal record; require hash + ingest pass |
| `orphan_unknown_count` | Files in staging with no corresponding journal or registry entry |
| `quarantined_count` | Files quarantined due to zero-byte or integrity check failures |

Zero-byte files discovered during ingest are quarantined (moved to a quarantine directory)
and an audit record is appended. They are never silently discarded.

---

## 15. Error Taxonomy and Resilience

> **Extracted** → [design/architecture/error-model.md](architecture/error-model.md)

The adapter layer defines a structured hierarchy of exceptions, all carrying loggable
fields without exposing sensitive material.

### Exception types

| Exception | Module | Meaning |
|-----------|--------|---------|
| `AuthError` | `adapters/onedrive/auth.py` | MSAL authentication failure (device-code flow, silent refresh) |
| `GraphError` | `adapters/onedrive/errors.py` | Microsoft Graph API request failure |
| `DownloadError` | `adapters/onedrive/errors.py` | File download failure (transport or HTTP error) |
| `GraphResyncRequired` | `adapters/onedrive/errors.py` | Graph delta returned `410 Gone`; cursor must be reset |

### URL/token redaction

All raise sites in the adapter call `redact_url()` before attaching a URL to an exception
or log record. The rules applied by `redact_url()`:

1. If the URL contains a query string, strip it entirely (pre-authenticated OneDrive
   download URLs embed bearer material as query parameters).
2. Truncate netloc+path to 80 characters for readability.
3. Never raise — if URL parsing fails, return a fixed sentinel `<unparseable-url>`.

Safe parameters (no query string) are logged at full length up to 120 characters.

### Retry policy

`RetryPolicy` (`adapters/onedrive/retry.py`) governs backoff for transient failures:

- Retryable status codes: 429, 500, 502, 503, 504 and any `Retry-After` response.
- `Retry-After` header is parsed and honoured (seconds or HTTP-date format).
- Exponential backoff with jitter; configurable max attempts and base delay.
- Non-retryable errors (4xx except 429, auth errors, resync) propagate immediately.

### Delta resync

On `GraphResyncRequired` (HTTP 410 from the Graph delta endpoint):
1. The current cursor is cleared.
2. The delta traversal restarts from `?token=latest`.
3. `resync_required_total` diagnostic counter is incremented.
4. Registry idempotency ensures no already-ingested files are re-processed.

### Auth resilience threshold

Consecutive authentication failures are counted per poll run. After ≥3 consecutive
failures (`auth_failure_threshold` in config), the runtime:
1. Writes a status snapshot with `state = "auth_failed"`.
2. Emits a structured log at ERROR level with `component = "auth"`.
3. Stops the current poll run (does not retry further).

Diagnostic counters tracked per run: `auth_refresh_attempt_total`,
`auth_refresh_success_total`, `auth_refresh_failure_total`.

### Throughput bounds

Two soft bounds prevent poll runs from consuming unbounded time or I/O:

- `max_downloads_per_poll`: when the per-run download count reaches this limit, the
  current page is committed and the poll terminates cleanly. The cursor is advanced to
  the last committed page; the next scheduled run resumes from there.
- `max_poll_runtime_seconds`: wall-clock timeout. Same clean-commit behaviour applies.

Neither bound raises an exception; both result in an orderly, auditable stop.

---

## 16. Observability Internals

> **Extracted** → [design/architecture/observability.md](architecture/observability.md)

### Structured logging

Every log record emitted by the service is structured. In JSON mode (`--log-mode json`),
each line is a JSON object with at minimum:

```json
{
  "ts": "2026-04-03T12:00:00.000000+00:00",
  "level": "INFO",
  "component": "onedrive.client",
  "msg": "...",
  "run_id": "...",
  "account": "christopher"
}
```

Context fields appended where relevant: `sha256`, `filename`, `status`, `onedrive_id`,
`action`, `actor`, `reason`.

In human mode (`--log-mode human`, default for interactive use), records are plain text
but carry the same fields. Both modes feed into journald via stdout.

### Run-ID

A UUID is generated once per poll invocation and propagated to:
- All log records emitted during that run
- `ingest_terminal_audit` rows (`batch_run_id` column)
- Status snapshot `details`

This enables cross-surface correlation: a single `run_id` links journal log lines,
audit rows, and the status snapshot produced by one poll cycle.

### Diagnostic counters

The following counters are accumulated per poll run inside `GraphClient` and emitted
via structured logs and the status snapshot `details` block on run completion:

| Counter key | Meaning |
|-------------|---------|
| `retry_attempt_total` | Total retry attempts made |
| `retry_transport_error_total` | Transport-layer errors that triggered retries |
| `throttle_response_total` | HTTP 429 / Retry-After responses received |
| `resync_required_total` | Delta resync (410 Gone) events |
| `auth_refresh_attempt_total` | MSAL silent refresh attempts |
| `auth_refresh_success_total` | Successful token refreshes |
| `auth_refresh_failure_total` | Failed token refreshes |
| `graph_response_request_id_seen_total` | Graph responses carrying `request-id` headers |
| `graph_response_correlation_id_seen_total` | Graph responses carrying `client-request-id` headers |

### Safe logging

`sanitize_extra()` (`adapters/onedrive/safe_logging.py`) is applied to all `extra=`
dicts before they reach the logging handler. It strips any key whose name matches known
credential patterns (e.g. `token`, `access_token`, `sig`, `tempauth`). The function
never raises; on internal error it returns a sanitized sentinel instead.

### Status snapshot

Written atomically to `/run/nightfall-status.d/photo-ingress.json` (tmp file then
`os.replace()`) after each CLI command that modifies system state.

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | int | `1` — increment on breaking changes |
| `service` | string | always `"photo-ingress"` |
| `version` | string | package `__version__` |
| `host` | string | `socket.gethostname()` |
| `state` | string | see state values below |
| `success` | bool | whether the command succeeded |
| `command` | string | CLI subcommand that wrote this snapshot |
| `updated_at` | string | ISO-8601 UTC |
| `details` | object | command-specific data (counters, error info, etc.) |

State values and their operator meaning:

| State | Meaning |
|-------|---------|
| `healthy` | Last command completed successfully |
| `degraded` | Non-fatal error; service continues on next scheduled run |
| `auth_failed` | Authentication failed; token refresh required before next poll |
| `disk_full` | SSD staging dataset above threshold; manual intervention required |
| `ingest_error` | Ingest engine failed; check journal and audit log |
| `registry_corrupt` | SQLite registry integrity check failed; manual recovery required |
